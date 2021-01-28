# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2021 CS GROUP - France
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Création des événements corrélés dans la BDD et transmission au bus.
"""

from sqlalchemy import not_ , and_
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.orm import aliased
import logging

from twisted.internet import defer

from vigilo.correlator.context import Context
from vigilo.correlator.db_insertion import add_to_aggregate, merge_aggregates, \
                                            remove_from_all_aggregates

from vigilo.models.session import DBSession
from vigilo.models.tables import CorrEvent, Event, EventHistory
from vigilo.models.tables import SupItem, HighLevelService, StateName
from vigilo.models.tables import DependencyGroup, Dependency
from vigilo.models.tables.eventsaggregate import EventsAggregate

from vigilo.common.logging import get_logger
from vigilo.common.gettext import translate
from vigilo.common.conf import settings

_ = translate(__name__)
LOGGER = get_logger(__name__)

__all__ = ('make_correvent', )


class CorrEventBuilder(object):
    """
    Crée, agrège et désagrège les événements corrélés.

    @cvar context_factory: Factory utilisée pour créer des L{Context}.
    """

    context_factory = Context

    def __init__(self, publisher, database):
        """
        Initialiseur de la classe.

        @param publisher: Objet de publication à utiliser pour envoyer
            des messages sur le bus.
        @param database: Objet pour les interactions avec la base de données.
        """
        self.publisher = publisher
        self.database = database

        try:
            self.log_level = settings['correlator'].as_int('syslog_data_level')
        except KeyError:
            self.log_level = logging.INFO

        data_logger = get_logger('vigilo.correlator.syslog')
        if data_logger.isEnabledFor(self.log_level):
            self.data_logger = data_logger
        else:
            self.data_logger = None


    @defer.inlineCallbacks
    def _get_update_id(self, item_id):
        """
        Retourne l'identifiant de l'événement corrélé ouvert
        pour l'identifiant d'objet donné.

        @param item_id: Identifiant de l'objet supervisé.
        @type item_id: C{int}
        @return: Identifiant de l'événement corrélé encore ouvert
            concernant cet objet ou C{None} s'il n'en existe aucun.
        @rtype: C{int}
        """
        state_ok = yield self.database.run(
            StateName.statename_to_value,
            u'OK',
            transaction=False
        )
        state_up = yield self.database.run(
            StateName.statename_to_value,
            u'UP',
            transaction=False
        )

        update_id = yield self.database.run(
            DBSession.query(
                CorrEvent.idcorrevent
            ).join(
                (Event, CorrEvent.idcause == Event.idevent),
                (SupItem, SupItem.idsupitem == Event.idsupitem),
            ).filter(SupItem.idsupitem == item_id
            ).filter(
                not_(and_(
                    Event.current_state.in_([state_ok, state_up]),
                    CorrEvent.ack == CorrEvent.ACK_CLOSED
                ))
            ).first,
            transaction=False
        )
        if update_id:
            res = update_id.idcorrevent
        else:
            res = None
        defer.returnValue(res)

    @defer.inlineCallbacks
    def _get_updated_correvent(self, update_id, timestamp):
        """
        Retourne l'instance de l'événement corrélé
        devant être mise à jour.

        @param update_id: Identifiant de l'événement corrélé à retourner.
        @type update_id: C{int}
        @param timestamp: Horodatage de l'événement en cours de traitement.
        @type timestamp: C{datetime.DateTime}
        @return: Deferred avec l'instance de l'événement corrélé
            à mettre à jour, ou C{None} si un nouvel événement
            doit être créé.
        @rtype: L{CorrEvent}
        """
        correvent = yield self.database.run(
            DBSession.query(
                CorrEvent
            ).filter(CorrEvent.idcorrevent == update_id
            ).one,
            transaction=False
        )

        if correvent:
            if correvent.timestamp_active > timestamp:
                LOGGER.info(_('Ignoring request to update correlated event %r: '
                              'a more recent update already exists in the '
                              'database'), update_id)
                defer.returnValue(None)

            LOGGER.debug(_('Updating existing correlated event (%r)'),
                           update_id)
        else:
            LOGGER.error(_('Got a reference to a non-existent '
                           'correlated event (%r), adding as new'),
                           update_id)
        defer.returnValue(correvent)

    @defer.inlineCallbacks
    def _aggregate_topologically(self, ctx, correvent, raw_event_id, item_id):
        """
        Procède à une première passe d'agrégation topologique,
        basée sur les agrégats prédécesseurs de l'alerte courante.

        @param ctx: Contexte de corrélation.
        @type ctx: L{Context}
        @param raw_event_id: Identifiant de l'événement brut.
        @type raw_event_id: C{int}
        @param item_id: Identifiant de l'objet supervisé concerné.
        @type item_id: C{int}
        @return: Deferred indiquant si l'événement corrélé a été agrégé
            dans un autre (C{True}) ou non (C{False}).
        @rtype: L{bool}
        """
        # Ajoute l'alerte aux agrégats prédécesseurs dont elle dépend.
        predecessing_aggregates_id = yield ctx.get('predecessors_aggregates')
        if not predecessing_aggregates_id:
            defer.returnValue(False)

        succeeding_aggregates_id = yield ctx.get('successors_aggregates')
        dependent_event_list = set()
        is_built_dependent_event_list = False
        predecessors_count = 0

        # Pour chaque agrégat dont l'alerte dépend,
        for predecessing_aggregate_id in predecessing_aggregates_id:
            predecessing_aggregate_id = int(predecessing_aggregate_id)
            try:
                yield self.database.run(
                    DBSession.query(CorrEvent).filter(
                        CorrEvent.idcorrevent == predecessing_aggregate_id
                    ).one,
                    transaction=False,
                )
                predecessors_count += 1
            except NoResultFound:
                LOGGER.error(_('Got a reference to a nonexistent '
                        'correlated event (%r), skipping this aggregate'),
                        int(predecessing_aggregate_id))

            else:
                # D'abord on rattache l'alerte
                # courante à cet agrégat dans la BDD.
                yield add_to_aggregate(
                    raw_event_id,
                    predecessing_aggregate_id,
                    self.database,
                    ctx,
                    item_id,
                    merging=True
                )

                # Ensuite on fusionne les éventuels agrégats
                # dépendant de l'alerte courante avec cet agrégat.
                if succeeding_aggregates_id:
                    for succeeding_aggregate_id in succeeding_aggregates_id:
                        events = yield merge_aggregates(
                            int(succeeding_aggregate_id),
                            predecessing_aggregate_id,
                            self.database,
                            ctx
                        )
                        if not is_built_dependent_event_list:
                            dependent_event_list.update(events)
                            is_built_dependent_event_list = True

        # On rattache l'alerte courante aux agrégats sur le bus.
        yield self.publisher.publish_aggregate(
                          predecessing_aggregates_id, [raw_event_id])

        if succeeding_aggregates_id:
            # On publie également sur le bus la
            # liste des alertes brutes (dépendantes de
            # l'alerte courante) à rattacher à ces agrégats.
            yield self.publisher.publish_aggregate(
                predecessing_aggregates_id,
                list(dependent_event_list))
            # Enfin on supprime du bus les agrégats
            # qui dépendaient de l'alerte courante.
            yield self.publisher.delete_published_aggregates(succeeding_aggregates_id)

        if correvent:
            # On supprime l'agrégat courant (fusionné dans ses prédécesseurs).
            LOGGER.debug('Deleting obsolete aggregate #%d', correvent.idcorrevent)
            yield self.database.run(
                DBSession.query(CorrEvent).filter(
                    CorrEvent.idcorrevent == correvent.idcorrevent).delete,
                transaction=False
            )
            yield self.publisher.delete_published_aggregates(correvent.idcorrevent)

        yield self.database.run(DBSession.flush, transaction=False)
        defer.returnValue(predecessors_count != 0)

    @defer.inlineCallbacks
    def _fill_with_context(self, ctx, info_dictionary, correvent, timestamp):
        """
        Renseigne les champs d'un événement corrélé et ceux
        du dictionnaire d'information à partir des données
        du contexte de corrélation.

        @param ctx: Contexte de corrélation.
        @type ctx: L{Context}
        @param info_dictionary: Dictionnaire d'information sur l'événement
            en cours de traitement.
        @type info_dictionary: C{dict}
        @param correvent: Événement corrélé à alimenter.
        @type correvent: L{CorrEvent}
        @param timestamp: Horodatage de l'événement.
        @type timestamp: C{datetime.DateTime}
        """
        # Priorité de l'incident.
        priority = yield ctx.get('priority')
        if priority is None:
            priority = settings['correlator'].as_int('unknown_priority_value')
        correvent.priority = priority
        info_dictionary["priority"] = priority

        # Nombre d'occurrences du problème.
        occurrences = yield ctx.get('occurrences_count')
        if not occurrences is None:
            correvent.occurrence = occurrences
            info_dictionary["occurrence"] = occurrences

        # Stockage des services de haut niveau impactés.
        impacted_hls = yield ctx.get('impacted_hls')
        info_dictionary["highlevel"] = []
        if impacted_hls:
            for hls in impacted_hls:
                service = yield self.database.run(
                    DBSession.query(HighLevelService.servicename
                    ).filter(HighLevelService.idservice == hls
                    ).first,
                    transaction=False
                )
                if service:
                    info_dictionary["highlevel"].append(service.servicename)
                else:
                    LOGGER.debug('Could not find impacted HLS with id #%d', hls)

        # Nouvel événement, on met à jour la date.
        if correvent.timestamp_active is None:
            correvent.timestamp_active = timestamp

    @defer.inlineCallbacks
    def _handle_closed_correvent(self, ctx, correvent, state, timestamp, item_id):
        """
        Traite un événement corrélé dont l'état d'acquittement
        vaut "Acquitté" ou "Acquitté et clos".

        @param ctx: Contexte de corrélation.
        @type ctx: L{Context}
        @param correvent: Evénement corrélé sur lequel on opère.
        @type correvent: L{CorrEvent}
        @param state: État de l'événement.
        @type state: C{str}
        @param timestamp: Horodatage de l'événement.
        @type timestamp: C{datetime.DateTime}
        @param item_id: Identifiant de l'objet supervisé sur lequel
            l'événement est survenu.
        @type item_id: C{int}
        """
        # On repasse l'événement dans l'état non-acquitté si un nouvel état
        # en erreur arrive et que le ticket avait été marqué comme "acquitté"
        # ou "acquitté et clos".
        if state not in ("OK", "UP"):
            correvent.timestamp_active = timestamp
            history = EventHistory(
                type_action=u'Acknowlegement change state',
                idevent=correvent.idcause,
                value=u'None',
                text=u'System forced treatment to None. '
                     u'Reason: Event was reactivated due to new outage',
                timestamp=timestamp,
                username=None,
            )
            yield self.database.run(DBSession.add, history, transaction=False)
            correvent.ack = CorrEvent.ACK_NONE

        # Si l'événement a été marqué comme traité et que le nouveau état
        # indique la résolution effective du problème, l'événement corrélé
        # doit être fermé.
        else:
            yield ctx.setShared('open_aggr:%d' % item_id, 0)

    @defer.inlineCallbacks
    def _disaggregate(self, ctx, correvent, update_id, timestamp):
        """
        Procède à la désagrégation de l'événement corrélé courant.

        @param ctx: Contexte de corrélation.
        @type ctx: L{Context}
        @param correvent: Événement corrélé en cours de modification.
        @type correvent: L{CorrEvent}
        @param update_id: Identifiant de l'événement corrélé courant.
        @type update_id: C{int}
        @param timestamp: Horodatage de l'événement.
        @type timestamp: C{datetime.DateTime}
        """
        cause = aliased(Event)
        others = aliased(Event)
        # On détermine les causes des nouveaux événements corrélés
        # (ceux obtenus par désagrégation de l'événement courant).
        new_causes = yield self.database.run(
            DBSession.query(
                EventsAggregate.idevent,
                DependencyGroup.iddependent,
            ).join(
                (CorrEvent,
                    CorrEvent.idcorrevent == EventsAggregate.idcorrevent),
                (others, others.idevent == EventsAggregate.idevent),
                (DependencyGroup,
                    DependencyGroup.iddependent == others.idsupitem),
                (Dependency, Dependency.idgroup == DependencyGroup.idgroup),
                (cause, cause.idevent == CorrEvent.idcause),
            ).filter(EventsAggregate.idevent != CorrEvent.idcause
            ).filter(Dependency.idsupitem == cause.idsupitem
            ).filter(Dependency.distance == 1
            ).filter(DependencyGroup.role == u'topology'
            ).filter(CorrEvent.idcorrevent == update_id).all,
            transaction=False
        )

        # Pour chacune des nouvelles causes, on crée
        # le nouvel événement corrélé.
        for new_cause in new_causes:
            LOGGER.debug(_('Creating new aggregate with cause #%(cause)d '
                           '(#%(supitem)d) from aggregate #%(original)d'),
                           {
                                'original': update_id,
                                'cause': new_cause.idevent,
                                'supitem': new_cause.iddependent,
                            })
            # Inutile d'appeler remove_from_all_aggregates() ici
            # car on désagrège déjà manuellement l'agrégat initial.
            new_correvent = CorrEvent(
                idcause=new_cause.idevent,
                priority=settings['correlator'].as_int(
                            'unknown_priority_value'),
                # On ne recopie pas le ticket d'incident
                # et on place l'événement corrélé dans
                # l'état d'acquittement initial.
                ack=CorrEvent.ACK_NONE,
                occurrence=1,
                timestamp_active=timestamp, # @XXX: ou datetime.utcnow() ?
            )
            yield self.database.run(
                DBSession.add, new_correvent,
                transaction=False,
            )

            # Retrait de l'événement brut cause des autres agrégats.
            yield self.database.run(
                DBSession.query(
                    EventsAggregate
                ).filter(EventsAggregate.idevent == new_cause.idevent,
                ).filter(EventsAggregate.idcorrevent != update_id
                ).delete,
                transaction=False,
            )

            yield self.database.run(
                DBSession.flush,
                transaction=False,
            )

            # On ajoute à cet agrégat les événements bruts
            # qui s'y rapportent (cf. topologie réseau).
            raw_events = yield self.database.run(
                DBSession.query(
                    Event.idevent,
                    Event.idsupitem,
                ).join(
                    (DependencyGroup,
                        DependencyGroup.iddependent == Event.idsupitem),
                    (Dependency, Dependency.idgroup == DependencyGroup.idgroup),
                    (EventsAggregate, EventsAggregate.idevent == Event.idevent),
                ).filter(Dependency.idsupitem == new_cause.iddependent
                ).filter(DependencyGroup.role == u'topology'
                ).filter(EventsAggregate.idcorrevent == update_id).all,
                transaction=False,
            )
            for raw_event in raw_events:
                yield add_to_aggregate(
                    raw_event.idevent,
                    new_correvent.idcorrevent,
                    self.database,
                    ctx,
                    raw_event.idsupitem,
                    merging=False
                )

            # Association de l'événement brut cause dans le nouvel agrégat.
            yield add_to_aggregate(
                new_cause.idevent,
                new_correvent.idcorrevent,
                self.database,
                ctx,
                new_cause.iddependent,
                merging=False
            )
            # @XXX: redemander l'état de l'équipement à Nagios ?

        # Prise en compte des modifications précédentes.
        yield self.database.run(DBSession.flush, transaction=False)

        # Suppression de l'association entre l'ancien agrégat
        # et les événements bruts qu'il contenait (sauf pour sa cause).
        yield self.database.run(
            DBSession.query(EventsAggregate
                ).filter(EventsAggregate.idcorrevent == update_id
                ).filter(EventsAggregate.idevent != correvent.idcause
                ).delete,
            transaction=False,
        )
        yield self.database.run(DBSession.flush, transaction=False)

    def _log_correvent(self, info_dictionary):
        """
        Enregistre un résumé du traitement de l'événement
        dans les journaux système.

        @param info_dictionary: Dictionnaire contenant les informations
            sur l'événement courant.
        @type info_dictionary: C{dict}
        """
        self.data_logger and self.data_logger.log(
                        self.log_level,
                        '%s|%s|%s|%s|%s|%s|%s',
                        info_dictionary['idcorrevent'],
                        info_dictionary['update'] and
                            'CHANGE' or 'NEW',
                        info_dictionary['host'],
                        info_dictionary['service'] or '',
                        info_dictionary['state'],
                        info_dictionary['priority'],
                        info_dictionary.get('message', ''),
                    )

    @defer.inlineCallbacks
    def _aggregate_successors(self, ctx, idcorrevent):
        """
        Procède à l'agrégation des successeurs de l'événement
        corrélé courant.

        @param ctx: Contexte de corrélation.
        @type ctx: L{Context}
        @param idcorrevent: Identifiant de l'événement corrélé courant.
        @type idcorrevent: C{int}
        """
        # Si un ou plusieurs agrégats dépendant de l'alerte sont
        # spécifiés dans le contexte par la règle de corrélation
        # topologique des services de bas niveau (lls_dep), alors
        # on rattache ces agrégats à l'agrégat nouvellement créé.
        aggregates_id = yield ctx.get('successors_aggregates')
        if aggregates_id:
            event_id_list = []
            for aggregate_id in aggregates_id:
                events_id = yield merge_aggregates(
                    int(aggregate_id),
                    idcorrevent,
                    self.database,
                    ctx
                )
                if events_id:
                    event_id_list.extend(events_id)
            # On publie sur le bus la liste des alertes brutes
            # à rattacher à l'événement corrélé nouvellement créé.
            yield self.publisher.publish_aggregate([idcorrevent], event_id_list)
            yield self.publisher.delete_published_aggregates(aggregates_id)

    @defer.inlineCallbacks
    def make_correvent(self, info_dictionary):
        """
        Récupère dans le contexte les informations transmises par
        les règles, crée les événements corrélés (agrégats d'événements)
        nécessaires dans la base de données et les transmet au bus.

        Permet de satisfaire les exigences suivantes :
            - VIGILO_EXIG_VIGILO_COR_0040,

        @param info_dictionary: Dictionnaire contenant les informations
            concernant l'événement en cours de trairement.
        @type info_dictionary: C{dict}
        @return: Instance de l'événement corrélé créé ou mis à jour
            ou C{None} si le traitement n'a pas engendré la création
            ni la mise à jour d'un événement corrélé.
        @rtype: L{CorrEvent}
        """
        ctx = self.context_factory(info_dictionary["id"], transaction=False)
        raw_event_id = yield ctx.get('raw_event_id')

        # Il peut y avoir plusieurs raisons à l'absence d'un ID brut :
        # - l'alerte brute portait sur un HLS; dans ce cas il ne s'agit pas
        #   vraiment d'une erreur (on n'enregistre pas d'événement corrélé).
        # - l'alerte brute portait sur un élément non configuré; dans ce cas il
        #   s'agit d'une véritable erreur, mais le log est déjà enregistré dans
        #   db_insertion.py. Inutile de répéter les logs ici.
        # - l'alerte indique un état UP/OK et aucun événement déjà ouvert n'a
        #   pu être trouvé. Inutile d'alerter l'opérateur car tout va bien.
        #   Un log est enregistré dans db_insertion.py et on peut ignorer le
        #   problème ici.
        if raw_event_id is None:
            defer.returnValue(None)

        state = info_dictionary['state']
        timestamp = info_dictionary['timestamp']

        # Si une règle ou un callback demande explicitement qu'aucune
        # alerte ne soit générée pour cet événement, on lui obéit ici.
        stop = yield ctx.get('no_alert')
        if stop:
            hostname = info_dictionary['host']
            servicename = info_dictionary['service']
            LOGGER.info(_(
                'Ignoring event #%(idevent)d on (%(host)r, %(service)r) '
                'as requested by the correlation rules') % {
                    'idevent': raw_event_id,
                    'host': hostname,
                    'service': servicename,
            })
            defer.returnValue(None)

        item_id = yield ctx.get('idsupitem')

        # Identifiant de l'événement corrélé à mettre à jour.
        update_id = yield self._get_update_id(item_id)

        correvent = None
        if update_id is not None:
            # On récupère l'événement corrélé existant pour mise à jour.
            correvent = yield self._get_updated_correvent(update_id, timestamp)

        # Il s'agit d'une création ou bien l'événement corrélé
        # indiqué n'existe pas.
        if correvent is None:
            update_id = None

            # Si l'état de l'alerte brute est 'OK' ou 'UP', on ne fait rien.
            if state in ("OK", "UP"):
                LOGGER.info(_('Raw event ignored. Reason: status = %r'), state)
                defer.returnValue(None)

        aggregated = yield self._aggregate_topologically(ctx, correvent, raw_event_id,
                                                             item_id)
        if aggregated:
           LOGGER.debug("Event #%d masked due to topological aggregation",
                        raw_event_id)
           defer.returnValue(None)

        if correvent is None:
            # Lorsqu'un nouvel agrégat doit être créé, il se peut que la cause
            # ait anciennement fait partie d'autres agrégats désormais OK/UP.
            # On doit supprimer ces associations avant de continuer (cf. #1027).
            yield remove_from_all_aggregates(raw_event_id, self.database)

            # Création du nouvel agrégat à partir de son événement cause.
            LOGGER.debug(_('Creating a new correlated event'))
            correvent = CorrEvent()
            correvent.idcause = raw_event_id

        # On remplit l'événement corrélé et le dictionnaire d'infos
        # à partir du contexte de corrélation.
        yield self._fill_with_context(ctx, info_dictionary,
                                      correvent, timestamp)

        if correvent.ack == CorrEvent.ACK_CLOSED:
            yield self._handle_closed_correvent(ctx, correvent, state,
                                                timestamp, item_id)

        # On sauvegarde l'événement corrélé dans la base de données.
        yield self.database.run(DBSession.add, correvent, transaction=False)
        yield self.database.run(DBSession.flush, transaction=False)

        # Récupération de l'identifiant de l'agrégat pour plus tard.
        # Doit être fait via db_thread. En pratique, cela signifie qu'on
        # doit faire un merge() pour fetcher à nouveau tous les attributs
        # avant de pouvoir y accéder depuis le thread principal.
        correvent = yield self.database.run(
            DBSession.merge,
            correvent,
            transaction=False)
        idcorrevent = correvent.idcorrevent

        # Ajout de l'alerte brute dans l'agrégat.
        yield add_to_aggregate(
            raw_event_id,
            idcorrevent,
            self.database,
            ctx,
            item_id,
            merging=False
        )

        if update_id is None:
            info_dictionary['update'] = False
            info_dictionary['idcorrevent'] = idcorrevent
        else:
            info_dictionary['update'] = True
            info_dictionary['idcorrevent'] = update_id
            info_dictionary['ticket_id'] = correvent.trouble_ticket
            info_dictionary['acknowledgement_status'] = correvent.ack

            if state in ('OK', 'UP'):
                # La cause de l'événement corrélé n'est plus en panne,
                # on tente de désagréger les événements bruts associés.
                yield self._disaggregate(ctx, correvent, update_id, timestamp)

        # On envoie le message correvent correspondant sur le bus
        # et on enregistre une trace dans les logs.
        yield self.publisher.sendMessage(info_dictionary)
        self._log_correvent(info_dictionary)

        yield self._aggregate_successors(ctx, idcorrevent)
        yield self.database.run(DBSession.flush, transaction=False)
        defer.returnValue(correvent)
