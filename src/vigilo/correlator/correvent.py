# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""
Création des événements corrélés dans la BDD et transmission à pubsub.
"""

from sqlalchemy import not_ , and_
from datetime import datetime
import logging

from sqlalchemy.orm.exc import NoResultFound
from lxml import etree

from vigilo.correlator.xml import namespaced_tag, NS_EVENTS
from vigilo.correlator.context import Context
from vigilo.correlator.db_insertion import add_to_aggregate, merge_aggregates
from vigilo.correlator.publish_messages import publish_aggregate, \
                                            delete_published_aggregates

from vigilo.correlator.compute_hls_states import compute_hls_states

from vigilo.models.configure import DBSession
from vigilo.models import CorrEvent, Event, EventHistory
from vigilo.models import SupItem, HighLevelService, StateName

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

def make_correvent(forwarder, xml):
    """
    Récupère dans le contexte les informations transmises par
    les règles, crée les événements corrélés (agrégats 
    d'événements) nécessaires dans la BDD et les transmet à pubsub.
    
    
    Permet de satisfaire les exigences suivantes : 
    - VIGILO_EXIG_VIGILO_COR_0040,
    - VIGILO_EXIG_VIGILO_COR_0060.
    """
    # Manière pas très propre de transformer le namespace
    # pour passer des tags <event>s aux <correvent>s.
    dom = etree.fromstring(xml)
    DBSession.flush()

    idnt = dom.get('id')
    dom = dom[0]
    ctx = Context(idnt)
    xml = etree.tostring(dom)
    raw_event_id = ctx.raw_event_id
    
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
        return

    # On détermine le nouvel état de chacun des HLS 
    # impactés par l'alerte, avant de l'enregistrer dans 
    # la BDD et de le transmettre à Nagios via le bus XMPP.
    compute_hls_states(forwarder, ctx)

    hostname = ctx.hostname
    servicename = ctx.servicename
    item_id = SupItem.get_supitem(hostname, servicename)

    update_id = DBSession.query(
                CorrEvent.idcorrevent
            ).join(
                (Event, CorrEvent.idcause == Event.idevent),
                (SupItem, SupItem.idsupitem == Event.idsupitem),
            ).filter(SupItem.idsupitem == item_id
            ).filter(not_(and_(
                Event.current_state.in_([
                    StateName.statename_to_value(u'OK'),
                    StateName.statename_to_value(u'UP')
                ]),
                CorrEvent.status == u'AAClosed'
            ))
            ).filter(CorrEvent.timestamp_active != None
            ).scalar()

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

    # Si il s'agit d'une mise à jour, on récupère l'événement
    # corrélé auquel elle se rapporte.
    if update_id is not None:
        try:
            correvent = DBSession.query(
                    CorrEvent
                ).filter(CorrEvent.idcorrevent == update_id
                ).one()
            LOGGER.debug(_('Updating existing correlated event (%r)') %
                update_id)
        except NoResultFound:
            LOGGER.error(_('Got a reference to a non-existent '
                'correlated event (%r), adding as new') % update_id)

    # Il s'agit d'une création ou bien l'événement corrélé
    # indiqué n'existe pas.
    if correvent is None:
        data_log[DATA_LOG_TYPE] = 'NEW'

        # Si l'état de l'alerte brute est 'OK' ou bien 'UP', on ne fait rien
        state = ctx.statename
        if state == "OK" or state == "UP":
            LOGGER.info(_('Raw event ignored. Reason: status = %r' 
                                % (state, )))
            return 

        # Si un ou plusieurs agrégats dont dépend l'alerte sont
        # spécifiés dans le contexte par la règle de corrélation
        # topologique des services de bas niveau (lls_dep),
        # alors on rattache l'alerte à ces agrégats.
        # Si un ou plusieurs agrégats dépendant de l'alerte sont
        # spécifiés dans le contexte par la règle de corrélation 
        # topologique des services de bas niveau (lls_dep), alors
        # on rattachera également les alertes correspondant à ces agrégats.
        predecessing_aggregates_id = ctx.predecessors_aggregates
        if predecessing_aggregates_id:
            succeeding_aggregates_id = ctx.successors_aggregates
            dependant_event_list = []
            is_built_dependant_event_list = False
            
            # Pour chaque agrégat dont l'alerte dépend,
            for predecessing_aggregate_id in predecessing_aggregates_id:
                try:
                    predecessing_aggregate = DBSession.query(CorrEvent
                        ).filter(CorrEvent.idcorrevent 
                                    == int(predecessing_aggregate_id)
                        ).one()

                except NoResultFound:
                    LOGGER.error(_('Got a reference to a nonexistent '
                            'correlated event (%r), skipping this aggregate')
                            % (int(predecessing_aggregate_id), ))

                else:
                    # D'abord on rattache l'alerte
                    # courante à cet agrégat dans la BDD.
                    add_to_aggregate(raw_event_id, predecessing_aggregate)
                    DBSession.flush()

                    # Ensuite on fusionne les éventuels agrégats
                    # dépendant de l'alerte courante avec cet agrégat.
                    if succeeding_aggregates_id:
                        for succeeding_aggregate_id in \
                                succeeding_aggregates_id:
                            events = merge_aggregates(
                                int(succeeding_aggregate_id),
                                int(predecessing_aggregate_id))
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

            DBSession.flush()
            return

        LOGGER.debug(_('Creating new correlated event'))
        
        correvent = CorrEvent()
        correvent.idcause = raw_event_id

    # Priorité de l'incident.
    priority = ctx.priority
    if priority is None:
        priority = settings['correlator'].as_int('unknown_priority_value')

    # Si l'événement avait déjà reçu une priorité,
    # on ne garde que la plus importante/critique.
    if correvent.priority is not None:
        if settings['correlator']['priority_order'] == 'asc':
            priority = min(priority, correvent.priority)
        else:
            priority = max(priority, correvent.priority)

    priority_tag = etree.SubElement(dom, "priority")
    priority_tag.text = str(priority)
    correvent.priority = priority

    # Nombre d'occurrences du problème.
    occurrences = ctx.occurrences_count
    if not occurrences is None:
        occurrence_tag = etree.SubElement(dom, "occurrence")
        occurrence_tag.text = str(occurrences)
        correvent.occurrence = occurrences

    # Identifiant de l'événement corrélé à mettre à jour.
    if not update_id is None:
        dom.set('update', str(update_id))

    # Stockage des services de haut niveau impactés.
    impacted_hls = ctx.impacted_hls
    highlevel_tag = etree.SubElement(dom, "highlevel")
    if impacted_hls:
        # On crée une liste de balises <service> sous la balise
        # <highlevel>. Ces balises <service> indiquent les noms
        # des services de haut niveau impactés par l'alerte.
        # On s'attend à ce que la liste contienne un nombre limité
        # d'éléments. Elle peut être vide si l'alerte n'impacte
        # aucun SHN.
        for hls in impacted_hls:
            service = DBSession.query(HighLevelService.servicename
                                    ).filter(HighLevelService.idservice == hls
                                    ).first()
            if service:
                service_tag = etree.SubElement(highlevel_tag, "service")
                service_tag.text = service.servicename
                data_log[DATA_LOG_IMPACTED_HLS].append(service.servicename)
    # Détermine le timestamp de l'événement.
    timestamp = dom.findtext(namespaced_tag(NS_EVENTS, "timestamp"))
    try:
        timestamp = datetime.fromtimestamp(int(timestamp))
    except (ValueError, TypeError):
        timestamp = datetime.now()

    # Nouvel événement, on met à jour la date.
    if correvent.timestamp_active is None:
        correvent.timestamp_active = timestamp

    # On repasse l'événement dans l'état non-acquitté.
    # Le test évite de polluer la BDD avec des changements d'acquittement.
    if (not correvent.status is None) and correvent.status != u'None':
        correvent.timestamp_active = timestamp
        history = EventHistory(
            type_action=u'Acknowlegement change state',
            idevent=correvent.idcause,
            value=u'None',
            text=u'System forced treatment to None. ' \
                'Reason: Event was reactivated due to new outage',
            timestamp=timestamp,
            username=None,
        )
        DBSession.add(history)
        correvent.status = u'None'

    # On sauvegarde l'événement corrélé dans la base de données.
    DBSession.add(correvent)
    DBSession.flush()

    # Ajout de l'alerte brute dans l'agrégat.
    add_to_aggregate(raw_event_id, correvent)

    # Récupération de l'identifiant de l'agrégat pour plus tard.
    idcorrevent = correvent.idcorrevent

    # On génère le message à envoyer à PubSub.
    payload = etree.tostring(dom)
    forwarder.sendItem(payload)

    # On génère le message à envoyer à syslog.
    # Ceci permet de satisfaire l'exigence VIGILO_EXIG_VIGILO_COR_0040.
    data_log[DATA_LOG_ID] = idcorrevent
    data_log[DATA_LOG_STATE] = ctx.statename
    data_log[DATA_LOG_PRIORITY] = priority
    data_log[DATA_LOG_HOST] = hostname
    data_log[DATA_LOG_SERVICE] = servicename
    data_log[DATA_LOG_MESSAGE] = dom.findtext(
        namespaced_tag(NS_EVENTS, 'message'), '')

    if not data_log[DATA_LOG_SERVICE]:
        data_log[DATA_LOG_SERVICE] = 'HOST'

    try:
        log_level = settings['correlator'].as_int('syslog_data_level')
    except KeyError:
        log_level = logging.INFO

    LOGGER.debug(_('Sending correlated event to syslog'))
    data_logger = get_logger('vigilo.correlator.syslog')
    data_logger.log(
        log_level,
        '%d|%s|%s|%s|%s|%d|%s',
        data_log[DATA_LOG_ID],
        data_log[DATA_LOG_TYPE],
        data_log[DATA_LOG_HOST],
        data_log[DATA_LOG_SERVICE],
        data_log[DATA_LOG_STATE],
        # @TODO: A réactiver si cela est souhaité
#        ';'.join(data_log[DATA_LOG_IMPACTED_HLS]),
        data_log[DATA_LOG_PRIORITY],
        data_log[DATA_LOG_MESSAGE],
    )

    # Si un ou plusieurs agrégats dépendant de l'alerte sont
    # spécifiés dans le contexte par la règle de corrélation
    # topologique des services de bas niveau (lls_dep), alors
    # on rattache ces agrégats à l'aggrégat nouvellement créé.
    aggregates_id = ctx.successors_aggregates
    if aggregates_id:
        event_id_list = []
        for aggregate_id in aggregates_id:
            events_id = merge_aggregates(int(aggregate_id), idcorrevent)
            if events_id:
                event_id_list.extend(events_id)
        # On publie sur le bus XMPP la liste des alertes brutes
        # à rattacher à l'événement corrélé nouvellement créé.
        publish_aggregate(forwarder, [idcorrevent], event_id_list)
        delete_published_aggregates(forwarder, aggregates_id)
    DBSession.flush()

