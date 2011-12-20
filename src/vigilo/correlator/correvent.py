# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Création des événements corrélés dans la BDD et transmission à pubsub.
"""

from sqlalchemy import not_ , and_
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.orm import aliased
from sqlalchemy.sql import functions
import logging

from lxml import etree
from twisted.internet import defer

from vigilo.pubsub.xml import namespaced_tag, NS_EVENT
from vigilo.correlator.context import Context
from vigilo.correlator.db_insertion import add_to_aggregate, merge_aggregates
from vigilo.correlator.publish_messages import publish_aggregate, \
                                            delete_published_aggregates

from vigilo.models.session import DBSession
from vigilo.models.tables import CorrEvent, Event, EventHistory
from vigilo.models.tables import SupItem, HighLevelService, StateName
from vigilo.models.tables.eventsaggregate import EventsAggregate

from vigilo.common.logging import get_logger
from vigilo.common.gettext import translate
from vigilo.common.conf import settings

_ = translate(__name__)
LOGGER = get_logger(__name__)

__all__ = ('make_correvent', )

DATA_LOG_TYPE = 0
DATA_LOG_ID = 1
DATA_LOG_HOST = 2
DATA_LOG_SERVICE = 3
DATA_LOG_STATE = 4
DATA_LOG_IMPACTED_HLS = 5
DATA_LOG_PRIORITY = 6
DATA_LOG_MESSAGE = 7

@defer.inlineCallbacks
def make_correvent(forwarder, database, dom, idnt, info_dictionary, context_factory=Context):
    """
    Récupère dans le contexte les informations transmises par
    les règles, crée les événements corrélés (agrégats
    d'événements) nécessaires dans la BDD et les transmet à pubsub.

    Permet de satisfaire les exigences suivantes :
        - VIGILO_EXIG_VIGILO_COR_0040,
        - VIGILO_EXIG_VIGILO_COR_0060.
    """
    ctx = context_factory(idnt, transaction=False)
    raw_event_id = yield ctx.get('raw_event_id')

    # Il peut y avoir plusieurs raisons à l'absence d'un ID d'évenement brut :
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
    hostname = info_dictionary['host']
    servicename = info_dictionary['service']
    timestamp = info_dictionary['timestamp']

    # Si une règle ou un callback demande explicitement qu'aucune
    # alerte ne soit générée pour cet événement, on lui obéit ici.
    stop = yield ctx.get('no_alert')
    if stop:
        LOGGER.info(_(
            'Ignoring event #%(idevent)d on (%(host)r, %(service)r) '
            'as requested by the correlation rules') % {
                'idevent': raw_event_id,
                'host': hostname,
                'service': servicename,
        })
        defer.returnValue(None)

    item_id = yield ctx.get('idsupitem')

    state_ok = yield database.run(
        StateName.statename_to_value,
        u'OK',
        transaction=False
    )
    state_up = yield database.run(
        StateName.statename_to_value,
        u'UP',
        transaction=False
    )

    update_id = yield database.run(
        DBSession.query(
            CorrEvent.idcorrevent
        ).join(
            (Event, CorrEvent.idcause == Event.idevent),
            (SupItem, SupItem.idsupitem == Event.idsupitem),
        ).filter(SupItem.idsupitem == item_id
        ).filter(
            not_(and_(
                Event.current_state.in_([state_ok, state_up]),
                CorrEvent.status == u'AAClosed'
            ))
        ).filter(CorrEvent.timestamp_active != None
        ).scalar,
        transaction=False
    )

    correvent = None
    data_log = [
        'CHANGE',   # TYPE
        '',         # ID
        '',         # HOTE
        '',         # SERVICE
        '',         # ETAT_SERVICE
        [],         # SERVICES_IMPACTES
        '',         # PRIORITE
        '',         # MESSAGE
    ]

    # S'il s'agit d'une mise à jour, on récupère l'événement
    # corrélé auquel elle se rapporte.
    if update_id is not None:
        correvent = yield database.run(
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

    # Il s'agit d'une création ou bien l'événement corrélé
    # indiqué n'existe pas.
    if correvent is None:
        data_log[DATA_LOG_TYPE] = 'NEW'

        # Si l'état de l'alerte brute est 'OK' ou 'UP', on ne fait rien.
        if state in ("OK", "UP"):
            LOGGER.info(_('Raw event ignored. Reason: status = %r'), state)
            defer.returnValue(None)

        # Si un ou plusieurs agrégats dont dépend l'alerte sont
        # spécifiés dans le contexte par la règle de corrélation
        # topologique des services de bas niveau (lls_dep),
        # alors on rattache l'alerte à ces agrégats.
        # Si un ou plusieurs agrégats dépendant de l'alerte sont
        # spécifiés dans le contexte par la règle de corrélation
        # topologique des services de bas niveau (lls_dep), alors
        # on rattachera également les alertes correspondant à ces agrégats.
        predecessing_aggregates_id = yield ctx.get('predecessors_aggregates')
        if predecessing_aggregates_id:
            succeeding_aggregates_id = yield ctx.get('successors_aggregates')
            dependant_event_list = []
            is_built_dependant_event_list = False

            # Pour chaque agrégat dont l'alerte dépend,
            for predecessing_aggregate_id in predecessing_aggregates_id:
                try:
                    predecessing_aggregate = yield database.run(
                        DBSession.query(CorrEvent).filter(
                            CorrEvent.idcorrevent ==
                                int(predecessing_aggregate_id)
                        ).one,
                        transaction=False,
                    )
                except NoResultFound:
                    LOGGER.error(_('Got a reference to a nonexistent '
                                    'correlated event (%r), skipping '
                                    'this aggregate'),
                                    int(predecessing_aggregate_id))

                else:
                    # D'abord on rattache l'alerte
                    # courante à cet agrégat dans la BDD.
                    yield add_to_aggregate(
                        raw_event_id,
                        predecessing_aggregate_id,
                        database,
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
                                int(predecessing_aggregate_id),
                                database,
                                ctx
                            )
                            if not is_built_dependant_event_list:
                                for event in events:
                                    if not event in dependant_event_list:
                                        dependant_event_list.append(event)

                        is_built_dependant_event_list = True

            # On rattache l'alerte courante aux agrégats sur le bus XMPP.
            publish_aggregate(forwarder,
                              predecessing_aggregates_id, [raw_event_id])

            if succeeding_aggregates_id:
                # On publie également sur le bus XMPP la
                # liste des alertes brutes (dépendantes de
                # l'alerte courante) à rattacher à ces agrégats.
                publish_aggregate(forwarder,
                            predecessing_aggregates_id, dependant_event_list)
                # Enfin on supprime du bus les agrégats
                # qui dépendaient de l'alerte courante.
                delete_published_aggregates(forwarder,
                                            succeeding_aggregates_id)

            yield database.run(DBSession.flush, transaction=False)
            defer.returnValue(None)

        LOGGER.debug(_('Creating a new correlated event'))

        correvent = CorrEvent()
        correvent.idcause = raw_event_id

    # Priorité de l'incident.
    priority = yield ctx.get('priority')
    if priority is None:
        priority = settings['correlator'].as_int('unknown_priority_value')

    priority_tag = etree.SubElement(dom, "priority")
    priority_tag.text = str(priority)
    correvent.priority = priority

    # Nombre d'occurrences du problème.
    occurrences = yield ctx.get('occurrences_count')
    if not occurrences is None:
        occurrence_tag = etree.SubElement(dom, "occurrence")
        occurrence_tag.text = str(occurrences)
        correvent.occurrence = occurrences

    # Stockage des services de haut niveau impactés.
    impacted_hls = yield ctx.get('impacted_hls')
    highlevel_tag = etree.SubElement(dom, "highlevel")
    if impacted_hls:
        # On crée une liste de balises <service> sous la balise
        # <highlevel>. Ces balises <service> indiquent les noms
        # des services de haut niveau impactés par l'alerte.
        # On s'attend à ce que la liste contienne un nombre limité
        # d'éléments. Elle peut être vide si l'alerte n'impacte
        # aucun SHN.
        for hls in impacted_hls:
            service = yield database.run(
                DBSession.query(HighLevelService.servicename
                ).filter(HighLevelService.idservice == hls
                ).first,
                transaction=False
            )
            if service:
                service_tag = etree.SubElement(highlevel_tag, "service")
                service_tag.text = service.servicename
                data_log[DATA_LOG_IMPACTED_HLS].append(service.servicename)

    # Nouvel événement, on met à jour la date.
    if correvent.timestamp_active is None:
        correvent.timestamp_active = timestamp

    if correvent.status == u'AAClosed':
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
                    'Reason: Event was reactivated due to new outage',
                timestamp=timestamp,
                username=None,
            )
            yield database.run(DBSession.add, history, transaction=False)
            correvent.status = u'None'

        # Si l'événement a été marqué comme traité et que le nouveau état
        # indique la résolution effective du problème, l'événement corrélé
        # doit être fermé.
        else:
            ctx.setShared('open_aggr:%d' % item_id, 0)

    # On sauvegarde l'événement corrélé dans la base de données.
    yield database.run(DBSession.add, correvent, transaction=False)
    yield database.run(DBSession.flush, transaction=False)

    # Récupération de l'identifiant de l'agrégat pour plus tard.
    # Doit être fait via db_thread. En pratique, cela signifie qu'on
    # doit faire un merge() pour fetcher à nouveau tous les attributs
    # avant de pouvoir y accéder depuis le thread principal.
    correvent = yield database.run(
        DBSession.merge,
        correvent,
        transaction=False)
    idcorrevent = correvent.idcorrevent

    # Ajout de l'alerte brute dans l'agrégat.
    yield add_to_aggregate(
        raw_event_id,
        idcorrevent,
        database,
        ctx,
        item_id,
        merging=False
    )

    # Identifiant de l'événement corrélé à mettre à jour.
    if update_id is None:
        dom.set('id', str(idcorrevent))
    else:
        dom.set('update', str(update_id))

        # La cause de l'événement corrélé n'est plus en panne,
        # on tente de désagréger les événements bruts associés.
        if state in ('OK', 'UP'):
            # On récupère les événements bruts de cet agrégat.
            raw_events = yield database.run(
                DBSession.query(
                    EventsAggregate.idevent
                ).filter(EventsAggregate.idcorrevent == update_id
                ).filter(EventsAggregate.idevent != correvent.idcause
                ).all,
                transaction=False
            )
            raw_events = [ev.idevent for ev in raw_events]

            # Pour chacun de ces événements bruts, on crée
            # un nouvel événement corrélé dont l'événement
            # brut est la cause.
            for raw_event in raw_events:
                LOGGER.debug(_('Creating new aggregate with cause #%(cause)d '
                                'from aggregate #%(original)d'), {
                                    'original': update_id,
                                    'cause': raw_event,
                                })
                new_correvent = CorrEvent(
                    idcause=raw_event,
                    impact=None,
                    priority=settings['correlator'].as_int(
                                'unknown_priority_value'),
                    # On ne recopie pas le ticket d'incident
                    # et on place l'événement corrélé dans
                    # l'état d'acquittement initial.
                    status=u'None',
                    occurrence=1,
                    timestamp_active=timestamp,
                )
                yield database.run(
                    DBSession.add, new_correvent,
                    transaction=False,
                )
                yield database.run(
                    DBSession.flush,
                    transaction=False,
                )

                # On supprime l'association entre l'événement brut
                # et l'ancien agrégat.
                yield database.run(
                    DBSession.query(
                        EventsAggregate
                    ).filter(EventsAggregate.idevent == raw_event
                    ).filter(EventsAggregate.idcorrevent !=
                                new_correvent.idcorrevent
                    ).delete,
                    transaction=False,
                )

                yield database.run(
                    DBSession.add,
                    EventsAggregate(
                        idevent=raw_event,
                        idcorrevent=new_correvent.idcorrevent
                    ),
                    transaction=False,
                )

                yield database.run(
                    DBSession.flush,
                    transaction=False,
                )

                # @XXX: redemander l'état de l'équipement à Nagios ?

    # On envoie le message <correvent> correspondant sur le bus.
    payload = etree.tostring(dom)
    forwarder.sendItem(payload)

    # @XXX: Ce code est spécifique à un client particulier,
    #       il vaudrait mieux utiliser un point d'entrée
    #       à la place pour obtenir un effet similaire.
    if state in (u'UP', u'OK'):
        log_priority = 0
    else:
        log_priority = priority

    # On génère le message à envoyer à syslog.
    # Ceci permet de satisfaire l'exigence VIGILO_EXIG_VIGILO_COR_0040.
    data_log[DATA_LOG_ID] = idcorrevent
    data_log[DATA_LOG_STATE] = state
    data_log[DATA_LOG_PRIORITY] = log_priority
    data_log[DATA_LOG_HOST] = hostname
    data_log[DATA_LOG_SERVICE] = servicename
    data_log[DATA_LOG_MESSAGE] = dom.findtext(
        namespaced_tag(NS_EVENT, 'message'), '')

    # Si l'événement porte sur l'hôte, il faut refléter cela.
    if not data_log[DATA_LOG_SERVICE]:
        data_log[DATA_LOG_SERVICE] = 'HOST'

    try:
        log_level = settings['correlator'].as_int('syslog_data_level')
    except KeyError:
        log_level = logging.INFO

    LOGGER.debug(_('Sending the correlated event to syslog'))
    data_logger = get_logger('vigilo.correlator.syslog')
    if data_logger.isEnabledFor(log_level):
        data_logger.log(
            log_level,
            '%d|%s|%s|%s|%s|%d|%s',
            data_log[DATA_LOG_ID],
            data_log[DATA_LOG_TYPE],
            data_log[DATA_LOG_HOST],
            data_log[DATA_LOG_SERVICE],
            data_log[DATA_LOG_STATE],
            # @TODO: A réactiver si cela est souhaité
#           ';'.join(data_log[DATA_LOG_IMPACTED_HLS]),
            data_log[DATA_LOG_PRIORITY],
            data_log[DATA_LOG_MESSAGE],
        )

    # Si un ou plusieurs agrégats dépendant de l'alerte sont
    # spécifiés dans le contexte par la règle de corrélation
    # topologique des services de bas niveau (lls_dep), alors
    # on rattache ces agrégats à l'aggrégat nouvellement créé.
    aggregates_id = yield ctx.get('successors_aggregates')
    if aggregates_id:
        event_id_list = []
        for aggregate_id in aggregates_id:
            events_id = yield merge_aggregates(
                int(aggregate_id),
                idcorrevent,
                database,
                ctx
            )
            if events_id:
                event_id_list.extend(events_id)
        # On publie sur le bus XMPP la liste des alertes brutes
        # à rattacher à l'événement corrélé nouvellement créé.
        publish_aggregate(forwarder, [idcorrevent], event_id_list)
        delete_published_aggregates(forwarder, aggregates_id)

    yield database.run(DBSession.flush, transaction=False)
    defer.returnValue(correvent)
