# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""
Extends pubsub clients to compute Node message.
"""

from sqlalchemy import not_, and_
from sqlalchemy.orm import aliased
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound
from sqlalchemy.exc import InvalidRequestError, IntegrityError

from vigilo.common.logging import get_logger
from vigilo.models.session import DBSession
from vigilo.models.tables import StateName, State, HLSHistory, SupItem
from vigilo.models.tables import Event, EventHistory, CorrEvent
from vigilo.models.tables.secondary_tables import EVENTSAGGREGATE_TABLE
from vigilo.common.gettext import translate

_ = translate(__name__)
LOGGER = get_logger(__name__)

__all__ = (
    'insert_event',
    'insert_state',
    'insert_hls_history',
    'add_to_aggregate',
    'merge_aggregates'
)


def insert_event(info_dictionary):
    """
    Insère un événement dans la BDD.
    Retourne l'identifiant de cet événement.

    @param info_dictionary: Dictionnaire contenant les informations
    extraites du message d'alerte reçu par le rule dispatcher.
    @type info_dictionary: C{dict}
    @return: L'identifiant de l'événement dans la BDD.
    @rtype: C{int}
    """

    # S'il s'agit d'un événement concernant un HLS.
    if not info_dictionary["host"]:
        LOGGER.error(_(u'Received request to add an event on HLS "%s"'),
                            info_dictionary["service"])
        return None

    # On récupère l'identifiant de l'item (hôte ou service) concerné.
    item_id = SupItem.get_supitem(info_dictionary["host"],
                                  info_dictionary["service"])
    if not item_id:
        LOGGER.error(_(u'Got a reference to a non configured item '
                       '(%(host)r, %(service)r), skipping event'), {
                            "host": info_dictionary["host"],
                            "service": info_dictionary["service"],
                        })
        return None

    history = EventHistory()
    try:
        # On recherche un éventuel évènement concernant
        # l'item faisant partie d'agrégats ouverts.
        cause_event = aliased(Event)
        current_event = aliased(Event)
        event = DBSession.query(
                    current_event
                ).join((EVENTSAGGREGATE_TABLE,
                        EVENTSAGGREGATE_TABLE.c.idevent ==
                            current_event.idevent)
                ).join((CorrEvent,
                        CorrEvent.idcorrevent ==
                            EVENTSAGGREGATE_TABLE.c.idcorrevent)
                ).join((cause_event,
                        cause_event.idevent == CorrEvent.idcause)
                ).filter(current_event.idsupitem == item_id
                ).filter(not_(and_(
                    cause_event.current_state.in_([
                        StateName.statename_to_value(u'OK'),
                        StateName.statename_to_value(u'UP')
                    ]),
                    CorrEvent.status == u'AAClosed'
                ))
                ).filter(CorrEvent.timestamp_active != None
                ).distinct().one()
        LOGGER.debug(_(u'Updating event %r'), event.idevent)
    # Si aucun événement correpondant à cet item ne figure dans la base
    except NoResultFound:
        # Si l'état de cette alerte est 'OK', on l'ignore
        if info_dictionary["state"] == "OK" or \
            info_dictionary["state"] == "UP":
            LOGGER.info(_(u'Ignoring request to create a new event '
                            'with state "%s" (nothing alarming here)'),
                            info_dictionary['state'])
            return None
        # Sinon, il s'agit d'un nouvel incident, on le prépare.
        event = Event()
        event.idsupitem = item_id
        history.type_action = u'New occurrence'
        LOGGER.debug(_(u'Creating new event'))
    except MultipleResultsFound:
        # Si plusieurs événements ont été trouvés
        LOGGER.error(_(u'Multiple matching events found, skipping.'))
        return None
    else:
        # Il s'agit d'une mise à jour.
        history.type_action = u'Nagios update state'

    # Mise à jour de l'évènement et préparation de l'historique.
    event.timestamp = info_dictionary['timestamp']
    event.current_state = StateName.statename_to_value(
                                                    info_dictionary['state'])
    history.value = info_dictionary['state']
    event.message = history.text = info_dictionary['message']
    history.timestamp = info_dictionary['timestamp']
    history.username = None

    try:
        # Sauvegarde de l'évènement.
        DBSession.add(event)
        DBSession.flush()

        history.idevent = event.idevent
        DBSession.add(history)
        DBSession.flush()

    # On capture les erreurs qui sont permanentes.
    except (IntegrityError, InvalidRequestError), e:
        LOGGER.exception(_(u'Got exception'))
        return None
    else:
        return event.idevent

def insert_hls_history(info_dictionary):
    """
    Insère le nouvel état du service de haut niveau dans HLSHistory
    afin de conserver une trace.

    @param info_dictionary: Dictionnaire contenant les informations
        extraites du message d'alerte reçu par le rule dispatcher.
    @type info_dictionary: C{dict}
    """

    # On récupère l'identifiant du service de haut niveau.
    item_id = SupItem.get_supitem(info_dictionary['host'],
                                    info_dictionary['service'])

    if not item_id:
        LOGGER.error(_(u'Got a reference to a non configured high-level '
                        'service (%(service)r)'), {
                            "service": info_dictionary["service"],
                        })
        return None

    history = HLSHistory()
    history.idhls = item_id
    history.timestamp = info_dictionary['timestamp']
    history.idstatename = StateName.statename_to_value(
                            info_dictionary['state'])
    try:
        DBSession.add(history)
        DBSession.flush()
    except IntegrityError, e:
        LOGGER.exception(_(u'Got exception'))

def insert_state(info_dictionary):
    """
    Insère l'état fourni par un message d'événement dans la BDD.

    Retourne cet état instancié.

    @param info_dictionary: Dictionnaire contenant les informations
    extraites du message d'alerte reçu par le rule dispatcher.
    @type info_dictionary: C{dict}
    """

    # On récupère l'identifiant de l'item (hôte ou service) concerné.
    item_id = SupItem.get_supitem(info_dictionary["host"],
                                  info_dictionary["service"])

    if not item_id:
        LOGGER.error(_(u'Got a reference to a non configured item '
                       '(%(host)r, %(service)r), skipping state'), {
                            "host": info_dictionary["host"],
                            "service": info_dictionary["service"],
                        })
        return None
    # On vérifie s'il existe déjà un état
    # enregistré dans la BDD pour cet item.
    state = DBSession.query(State
                ).filter(State.idsupitem == item_id
                ).first()
    # Le cas échéant, on le crée.
    if not state:
        state = State(idsupitem = item_id)

    previous_state = state.state

    # On met à jour l'état dans la BDD
    state.message = info_dictionary["message"]
    state.timestamp = info_dictionary["timestamp"]
    state.state = StateName.statename_to_value(info_dictionary["state"])

    try:
        DBSession.add(state)
        DBSession.flush()
    except (IntegrityError, InvalidRequestError):
        LOGGER.exception(_(u'Got exception'))
    return previous_state


def add_to_aggregate(idevent, aggregate):
    """
    Ajoute un événement brut à un événement corrélé.

    @param idevent: Identifiant de l'événement brut à ajouter.
    @type idevent: C{int}
    @param aggregate: Agrégat vers lequel se fait l'ajout.
    @type aggregate: L{vigilo.models.CorrEvent}
    """
    event = DBSession.query(Event).filter(Event.idevent == idevent).one()
    try:
        if not event in aggregate.events:
            aggregate.events.append(event)
            DBSession.flush()

    except (IntegrityError, InvalidRequestError):
        LOGGER.exception(_(u'Got exception'))


def merge_aggregates(sourceaggregateid, destinationaggregateid):
    """
    Fusionne deux agrégats. Renvoie la liste des identifiants
    des alertes brutes de l'agrégat source ainsi déplacées.

    @param sourceaggregateid: Identifiant de l'agrégat source.
    @type sourceaggregateid: C{int}
    @param destinationaggregateid: Identifiant de l'agrégat destination.
    @type destinationaggregateid: C{int}

    @return: Liste des ids des alertes brutes déplacées.
    @rtype: Liste de C{int}
    """
    sourceaggregateid = int(sourceaggregateid)
    LOGGER.debug(_(u'Merging aggregate #%(src)d with aggregate #%(dest)d'), {
                    'src': sourceaggregateid,
                    'dest': destinationaggregateid,
                })

    # Récupère l'agrégat source depuis la BDD.
    try:
        source_aggregate = DBSession.query(CorrEvent
                    ).filter(CorrEvent.idcorrevent == sourceaggregateid
                    ).one()
    except NoResultFound:
        LOGGER.exception(_(u'merge_aggregates: Got a reference to a nonexistent '
                       'source aggregate, aborting'))
        return

    # Récupère l'agrégat destination depuis la BDD.
    try:
        destination_aggregate = DBSession.query(CorrEvent
                ).filter(CorrEvent.idcorrevent == destinationaggregateid
                ).one()
    except NoResultFound:
        LOGGER.exception(_(u'merge_aggregates: Got a reference to a nonexistent '
                       'destination aggregate %r, aborting'),
                       destinationaggregateid)
        return

    # Déplace les événements depuis l'agrégat source
    # vers l'agrégat destination.
    event_id_list = []
    for event in source_aggregate.events:
        if not event in destination_aggregate.events:
            destination_aggregate.events.append(event)
            event_id_list.append(event.idevent)
            DBSession.flush()

    # Supprime l'agrégat source de la BDD.
    DBSession.delete(source_aggregate)

    DBSession.flush()
    return event_id_list
