# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Extends pubsub clients to compute Node message.
"""

from sqlalchemy import not_, and_, or_
from sqlalchemy.orm import aliased
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound

from twisted.internet import defer
from datetime import datetime

from vigilo.common.logging import get_logger
from vigilo.models.session import DBSession
from vigilo.models.tables import StateName, State, HLSHistory
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


class OldStateReceived(object):
    def __init__(self, current, received):
        self.current = current
        self.received = received

class NoProblemException(Exception):
    pass

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

    if not info_dictionary['idsupitem']:
        LOGGER.error(_(u'Got a reference to a non configured item '
                       '(%(host)r, %(service)r), skipping event'), {
                            "host": info_dictionary["host"],
                            "service": info_dictionary["service"],
                        })
        return None

    # On recherche un éventuel évènement brut concernant cet item.
    # L'événement doit être associé à un événement corrélé ouvert
    # ou bien ne pas être à rattaché à un événement corrélé du tout.
    cause_event = aliased(Event)
    current_event = aliased(Event)
    event = DBSession.query(
                current_event
            ).outerjoin(
                (EVENTSAGGREGATE_TABLE, EVENTSAGGREGATE_TABLE.c.idevent ==
                    current_event.idevent),
                (CorrEvent, CorrEvent.idcorrevent ==
                    EVENTSAGGREGATE_TABLE.c.idcorrevent),
                (cause_event, cause_event.idevent == CorrEvent.idcause),
            ).filter(current_event.idsupitem == info_dictionary['idsupitem']
            ).filter(
                or_(
                    # Soit l'événement brut n'est pas
                    # rattaché à un événement corrélé.
                    CorrEvent.idcorrevent == None,

                    # Soit l'événement corrélé auquel
                    # il est rattaché est toujours ouvert.
                    and_(
                        not_(
                            and_(
                                cause_event.current_state.in_([
                                    StateName.statename_to_value(u'OK'),
                                    StateName.statename_to_value(u'UP')
                                ]),
                                CorrEvent.status == u'AAClosed'
                            )
                        ),
                        CorrEvent.timestamp_active != None
                    )
                )
            # On privilégie les événements bruts
            # associés à un événement corrélé.
            ).order_by((CorrEvent.idcorrevent != None).desc()
            ).distinct().limit(2).all()

    # Si aucun événement correpondant à cet item ne figure dans la base
    if not event:
        # Si l'état de cette alerte est 'OK', on l'ignore
        if info_dictionary["state"] == "OK" or \
            info_dictionary["state"] == "UP":
            LOGGER.info(_('Ignoring request to create a new event '
                            'with state "%s" (nothing alarming here)'),
                            info_dictionary['state'])
            raise NoProblemException(info_dictionary.copy())
        # Sinon, il s'agit d'un nouvel incident, on le prépare.
        event = Event()
        event.idsupitem = info_dictionary['idsupitem']
        LOGGER.debug(_('Creating new event'))

    # Si plusieurs événements ont été trouvés
    else:
        if len(event) > 1:
            LOGGER.warning(_('Multiple raw events found, '
                             'using the first one available.'))
        event = event[0]
        LOGGER.debug(_('Updating event %r'), event.idevent)

    # Nouvel état.
    new_state_value = StateName.statename_to_value(info_dictionary['state'])
    is_new_event = event.idevent is None

    # Détermine si on doit ajouter une entrée dans l'historique.
    # On ajoute une entrée s'il s'agit d'un nouvel événement
    # ou si un champ autre que le timestamp a changé.
    add_history = is_new_event or \
                    event.current_state != new_state_value or \
                    event.message != info_dictionary['message']

    # Mise à jour de l'évènement.
    event.timestamp = info_dictionary['timestamp']
    event.current_state = new_state_value
    event.message = info_dictionary['message']

    # Sauvegarde de l'évènement.
    DBSession.add(event)

    if add_history:
        history = EventHistory()

        history.type_action = is_new_event and \
                                u'New occurrence' or \
                                u'Nagios update state'

        history.value = info_dictionary['state']
        history.text = info_dictionary['message']
        history.timestamp = info_dictionary['timestamp']
        history.username = None
        history.event = event
        DBSession.add(history)

    DBSession.flush()
    return event.idevent

def insert_hls_history(info_dictionary):
    """
    Insère le nouvel état du service de haut niveau dans HLSHistory
    afin de conserver une trace.

    @param info_dictionary: Dictionnaire contenant les informations
        extraites du message d'alerte reçu par le rule dispatcher.
    @type info_dictionary: C{dict}
    """

    if not info_dictionary['idsupitem']:
        LOGGER.error(_(u'Got a reference to a non configured high-level '
                        'service (%(service)r)'), {
                            "service": info_dictionary["service"],
                        })
        return None

    history = HLSHistory()
    history.idhls = info_dictionary['idsupitem']
    # On enregistre l'heure à laquelle le message a
    # été traité plutôt que le timestamp du message.
    history.timestamp = datetime.now()
    history.idstatename = StateName.statename_to_value(
                            info_dictionary['state'])
    DBSession.add(history)

def insert_state(info_dictionary):
    """
    Insère l'état fourni par un message d'événement dans la BDD.

    Retourne cet état instancié.

    @param info_dictionary: Dictionnaire contenant les informations
    extraites du message d'alerte reçu par le rule dispatcher.
    @type info_dictionary: C{dict}
    """

    if not info_dictionary['idsupitem']:
        LOGGER.error(_(u'Got a reference to a non configured item '
                       '(%(host)r, %(service)r), skipping state'), {
                            "host": info_dictionary["host"],
                            "service": info_dictionary["service"],
                        })
        return None

    # On vérifie s'il existe déjà un état
    # enregistré dans la BDD pour cet item.
    state = DBSession.query(State).get(info_dictionary['idsupitem'])

    # Le cas échéant, on le crée.
    if not state:
        state = State(idsupitem=info_dictionary['idsupitem'])
    elif state and state.timestamp > info_dictionary["timestamp"]:
        return OldStateReceived(state.timestamp, info_dictionary["timestamp"])

    previous_state = state.state

    # On met à jour l'état dans la BDD
    state.message = info_dictionary["message"]
    state.timestamp = info_dictionary["timestamp"]
    state.state = StateName.statename_to_value(info_dictionary["state"])

    DBSession.add(state)
    return previous_state


def add_to_aggregate(idevent, aggregate, database):
    """
    Ajoute un événement brut à un événement corrélé.

    @param idevent: Identifiant de l'événement brut à ajouter.
    @type idevent: C{int}
    @param aggregate: Agrégat vers lequel se fait l'ajout.
    @type aggregate: L{CorrEvent}
    """
    LOGGER.debug(_('Adding event #%(event)d to aggregate #%(aggregate)d'), {
                    'event': idevent,
                    'aggregate': aggregate.idcorrevent,
                })

    def add_event(idevent):
        event = DBSession.query(Event).get(idevent)

        if not event:
            raise ValueError, idevent

        if not event in aggregate.events:
            aggregate.events.append(event)
            DBSession.flush()
    return database.run(add_event, idevent, transaction=False)


def merge_aggregates(sourceaggregateid, destinationaggregateid, database, ctx):
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

    d = defer.DeferredList(
        [
            database.run(
                DBSession.query(CorrEvent).filter(
                    CorrEvent.idcorrevent == sourceaggregateid).one,
                transaction=False
            ),
            database.run(
                DBSession.query(CorrEvent).filter(
                    CorrEvent.idcorrevent == destinationaggregateid).one,
                transaction=False
            ),
        ],
        consumeErrors=True,
    )

    def eb(failure):
        if failure.check(NoResultFound):
            LOGGER.exception(_('Got a reference to a nonexistent aggregate, '
                                'aborting'))
            return
        return failure

    def delete(result, source_aggregate):
        # Supprime l'agrégat source de la BDD.
        return database.run(DBSession.delete, source_aggregate,
            transaction=False)

    def flush(result):
        return database.run(DBSession.flush, transaction=False)

    def merge(result):
        source, dest = result

        # Si l'aggrégat source n'a pas pu être trouvé.
        if not source[0]:
            return source[1]
        # Idem pour l'agrégat de destination.
        if not dest[0]:
            return dest[1]

        source_aggregate = source[1]
        destination_aggregate = dest[1]

        # Déplace les événements depuis l'agrégat source
        # vers l'agrégat destination.
        event_id_list = []
        defs = []

        for event in source_aggregate.events:
            if not event in destination_aggregate.events:
                defs.append(database.run(
                    destination_aggregate.events.append, event,
                    transaction=False,
                ))
                defs.append(ctx.setShared('open_aggr:%d' % event.idsupitem, 0))
                event_id_list.append(event.idevent)

        d = defer.DeferredList(defs)
        d.addCallback(delete, source_aggregate)
        d.addCallback(flush)
        d.addCallback(lambda res: event_id_list)
        return d

    d.addCallbacks(merge, eb)
    return d
