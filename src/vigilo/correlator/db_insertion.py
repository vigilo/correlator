# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2019 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Traite l'insertion en base de données.
"""

from sqlalchemy import not_, and_, or_
from sqlalchemy.orm import aliased

from twisted.internet import defer
from datetime import datetime

from vigilo.common.logging import get_logger
from vigilo.models.session import DBSession
from vigilo.models.tables import StateName, State, HLSHistory
from vigilo.models.tables import Event, EventHistory, CorrEvent
from vigilo.models.tables.secondary_tables import EVENTSAGGREGATE_TABLE
from vigilo.models.tables.eventsaggregate import EventsAggregate
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
        LOGGER.error(_('Received request to add an event on HLS "%s"'),
                            info_dictionary["service"])
        return None

    if not info_dictionary['idsupitem']:
        LOGGER.error(_('Got a reference to a non configured item '
                       '(%(host)r, %(service)r), skipping event'), {
                            "host": info_dictionary["host"],
                            "service": info_dictionary["service"],
                        })
        return None

    # Si on reçoit une notification sur un LLS indiquant que l'hôte est DOWN,
    # le message vient de Vigilo lui-même (cf. règle SvcHostDown) et on doit
    # l'ignorer pour éviter de générer une alerte pour rien.
    # L'état du service a déjà été mis à jour par la règle de corrélation.
    if info_dictionary['service'] and \
        info_dictionary['state'] == 'UNKNOWN' and \
        info_dictionary['message'] == u'Host is down':
        LOGGER.debug(_('Got a notification about an UNKNOWN state for '
                       'service "%(service)s" on unreachable host "%(host)s", '
                       'skipping event'), {
                            "host": info_dictionary["host"],
                            "service": info_dictionary["service"],
                       })
        return None

    # On recherche un éventuel évènement brut concernant cet item.
    # L'événement doit être associé à un événement corrélé ouvert
    # ou bien ne pas être à rattaché à un événement corrélé du tout.
    cause_event = aliased(Event)
    current_event = aliased(Event)
    # On privilégie les événements bruts associés à un événement corrélé.
    order_clause = (CorrEvent.idcorrevent != None)
    event = DBSession.query(
                current_event,
                order_clause,   # Doit être présent dans le SELECT
                                # pour satisfaire PostgreSQL.
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
                    not_(
                        and_(
                            cause_event.current_state.in_([
                                StateName.statename_to_value(u'OK'),
                                StateName.statename_to_value(u'UP')
                            ]),
                            CorrEvent.ack == CorrEvent.ACK_CLOSED
                        )
                    )
                )
            ).order_by(order_clause.desc()
            ).distinct().limit(2).all()

    # Si aucun événement correpondant à cet item ne figure dans la base
    if not event:
        # Si l'état de cette alerte est 'OK', on l'ignore
        if info_dictionary["state"] == "OK" or \
            info_dictionary["state"] == "UP":
            LOGGER.info(_('Ignoring request to create a new event '
                            'with state "%s" (nothing alarming here)'),
                            info_dictionary['state'])
            return None
        # Sinon, il s'agit d'un nouvel incident, on le prépare.
        event = Event()
        event.idsupitem = info_dictionary['idsupitem']
        LOGGER.debug(_('Creating new event'))

    # Si plusieurs événements ont été trouvés
    else:
        if len(event) > 1:
            LOGGER.warning(_('Multiple raw events found, '
                             'using the first one available.'))
        # On sélectionne le premier Event parmi la liste
        # des tuples (Event, CorrEvent.idcorrevent != None).
        event = event[0][0]
        LOGGER.debug(_('Updating event %r'), event.idevent)

    # Nouvel état.
    new_state_value = StateName.statename_to_value(info_dictionary['state'])
    is_new_event = event.idevent is None

    # S'agit-il d'un événement important ?
    # Un événement est important s'il s'agit d'un nouvel événement
    # ou si un champ autre que le timestamp ou le message a changé.
    info_dictionary['important'] = is_new_event or \
                                    event.current_state != new_state_value or \
                                    event.message != info_dictionary['message']


    # Mise à jour de l'évènement.
    event.timestamp = info_dictionary['timestamp']
    event.current_state = new_state_value
    event.message = info_dictionary['message']

    # Sauvegarde de l'évènement.
    DBSession.add(event)

    # Les événements importants donnent lieu à l'ajout
    # d'une entrée dans l'historique.
    if info_dictionary['important']:
        history = EventHistory()

        history.type_action = is_new_event and \
                                u'New occurrence' or \
                                u'Nagios update state'

        try:
            history.state = \
                StateName.statename_to_value(info_dictionary['state'])
        except KeyError:
            # Si le nom d'état n'est pas reconnu, on ne fait rien.
            pass

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
        LOGGER.error(_('Got a reference to a non configured high-level '
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
        LOGGER.error(_('Got a reference to a non configured item '
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


def add_to_aggregate(idevent, idcorrevent, database, ctx, idsupitem, merging):
    """
    Ajoute un événement brut à un événement corrélé.

    @param idevent: Identifiant de l'événement brut à ajouter.
    @type idevent: C{int}
    @param idcorrevent: Identifiant de l'agrégat auquel ajouter l'événement.
    @type idcorrevent: C{int}
    @param database: Objet qui encapsule les échanges avec la base de données.
    @type database: L{DatabaseWrapper}
    @param ctx: Contexte de corrélation.
    @type ctx: L{Context}
    @param idsupitem: Identifiant de l'élément supervisé (L{SupItem})
        sur lequel porte l'événement à ajouter à l'agrégat.
    @type idsupitem: C{int}
    @param merging: Indique si l'ajout a lieu au cours d'une fusion ou bien
        si l'ajout est le fait de la création d'un nouvel agrégat.
    @type merging: C{bool}

    @return: C{Deferred} qui sera appelé lorsque l'événement aura été
        ajouté à l'agrégat.
    @rtype: C{Deferred}
    """
    entry = database.run(
        DBSession.query(
            EVENTSAGGREGATE_TABLE
        ).filter(EVENTSAGGREGATE_TABLE.c.idevent == idevent
        ).filter(EVENTSAGGREGATE_TABLE.c.idcorrevent == idcorrevent
        ).first,
        transaction=False
    )

    def _update_cache(_result):
        """
        Met à jour l'entrée dans memcached qui indique l'événement corrélé
        ouvert qui impacte cet élément supervisé.
        """
        if merging:
            # Si on est en train de fusionner l'événement brut dans un événement
            # correlé ouvert plus général, alors il n'est pas la cause de cet
            # événement corrélé et n'a donc plus d'entrée associée.
            new_idcorrevent = 0
        else:
            # Sinon, il s'agit de la cause, donc on remplit le cache.
            new_idcorrevent = idcorrevent
        return ctx.setShared('open_aggr:%d' % idsupitem, new_idcorrevent)

    def _insert():
        LOGGER.debug(_('Adding event #%(event)d (supitem #%(supitem)d) '
                        'to aggregate #%(aggregate)d'), {
                        'event': idevent,
                        'supitem': idsupitem,
                        'aggregate': idcorrevent,
                    })

        DBSession.add(EventsAggregate(idevent=idevent, idcorrevent=idcorrevent))
        DBSession.flush()

    def _add_if_absent(has_entry):
        """
        Ajoute l'association entre l'événement brut et l'événement corrélé
        si aucune association de ce type n'existe pour le moment.
        """
        if has_entry:
            LOGGER.debug(_('Event #%(event)d already belongs to aggregate '
                            '#%(aggregate)d, refusing to add it twice'), {
                            'event': idevent,
                            'aggregate': idcorrevent,
                        })
            return

        d = database.run(_insert, transaction=False)
        d.addCallback(_update_cache)
        return d

    entry.addCallback(_add_if_absent)
    return entry

def remove_from_all_aggregates(idevent, database):
    """
    Supprime un événement de tous les agrégats où il apparaissait.

    @param idevent: Identifiant de l'événement à supprimer des agrégats.
    @type idevent: C{int}
    @param database: Objet qui encapsule les échanges avec la base de données.
    @type database: L{DatabaseWrapper}
    """
    # Ici, on n'utilise pas la forme ORM de delete() car EVENTSAGGREGATE_TABLE
    # n'est pas une table définie déclarativement.
    entry = database.run(
        EVENTSAGGREGATE_TABLE.delete(EVENTSAGGREGATE_TABLE.c.idevent == idevent
            ).execute,
        transaction=False
    )
    return entry

def merge_aggregates(sourceaggregateid, destinationaggregateid, database, ctx):
    """
    Fusionne deux agrégats. Renvoie la liste des identifiants
    des alertes brutes de l'agrégat source ainsi déplacées.

    @param sourceaggregateid: Identifiant de l'agrégat source.
    @type sourceaggregateid: C{int}
    @param destinationaggregateid: Identifiant de l'agrégat destination.
    @type destinationaggregateid: C{int}
    @param database: Objet qui encapsule les échanges avec la base de données.
    @type database: L{DatabaseWrapper}
    @param ctx: Contexte de corrélation.
    @type ctx: L{Context}

    @return: Liste des ids des alertes brutes déplacées.
    @rtype: Liste de C{int}
    """
    sourceaggregateid = int(sourceaggregateid)
    destinationaggregateid = int(destinationaggregateid)
    LOGGER.debug(_( 'Merging aggregate #%(src)d into aggregate #%(dest)d'), {
                    'src': sourceaggregateid,
                    'dest': destinationaggregateid,
                })

    d = defer.DeferredList(
        [
            database.run(
                DBSession.query(
                    Event.idsupitem,
                    EVENTSAGGREGATE_TABLE.c.idevent
                ).join(
                    (EVENTSAGGREGATE_TABLE, Event.idevent ==
                        EVENTSAGGREGATE_TABLE.c.idevent),
                ).filter(
                    EVENTSAGGREGATE_TABLE.c.idcorrevent == sourceaggregateid
                ).all,
                transaction=False
            ),
            database.run(
                DBSession.query(EVENTSAGGREGATE_TABLE.c.idevent).filter(
                EVENTSAGGREGATE_TABLE.c.idcorrevent == destinationaggregateid).all,
                transaction=False
            ),
        ],
        consumeErrors=True,
    )

    def _swap():
        """
        Déplace les événements bruts autrefois rattachés à l'événement
        corrélé source vers l'événement corrélé destination.

        Il n'y a pas de doublons possibles (un événement brut ne peut pas
        appartenir plusieurs fois au même événement corrélé).
        """
        # Bascule des événements de l'ancien agrégat vers le nouveau.
        # On utilise une sous-requête afin d'exclure les événements qui font
        # déjà partie de l'agrégat destination (pas de doublons possibles:
        # il y a une contrainte d'unicité).
        sub_select = DBSession.query(EventsAggregate.idevent).filter(
            EventsAggregate.idcorrevent == destinationaggregateid)

        DBSession.query(
                EventsAggregate
            ).filter(EventsAggregate.idcorrevent == sourceaggregateid
            ).filter(not_(EventsAggregate.idevent.in_(sub_select))
            ).update({"idcorrevent": destinationaggregateid},
                     synchronize_session='fetch')
        DBSession.flush()

    def _delete(_result):
        """Supprime l'agrégat source de la base de données."""
        return database.run(
            DBSession.query(CorrEvent).filter(
                CorrEvent.idcorrevent == sourceaggregateid).delete,
            transaction=False
        )

    def _merge(result):
        """
        Effectue la fusion à proprement parler:
        -   Le cache des agrégats ouverts est mis à jour.
        -   Les événements rattachés à l'ancien agrégat passent sur le nouveau.
        -   L'ancien agrégat est supprimé.
        """
        source, dest = result

        # S'il n'y a aucun événement dans l'aggrégat source,
        # c'est qu'il y a un problème.
        if not source[0] or not source[1]:
            LOGGER.warning(_('Got a reference to a nonexistent aggregate, '
                            'aborting'))
            return
        # Idem pour l'agrégat de destination.
        if not dest[0] or not dest[1]:
            LOGGER.warning(_('Got a reference to a nonexistent aggregate, '
                            'aborting'))
            return

        # Déplace les événements depuis l'agrégat source
        # vers l'agrégat destination.
        event_id_list = []
        defs = []

        # Mise à jour de l'agrégat ouvert associé au supitem dans memcached.
        for event in source[1]:
            defs.append(ctx.setShared('open_aggr:%d' % event.idsupitem, 0))
            LOGGER.debug(_("Event #%(event)d (supitem #%(supitem)d) will be "
                            "merged into aggregate #%(aggregate)d"), {
                            'event': event.idevent,
                            'supitem': event.idsupitem,
                            'aggregate': destinationaggregateid,
                        })
            event_id_list.append(event.idevent)

        defs.append(database.run(_swap, transaction=False))
        d = defer.DeferredList(defs)

        # Suppression de l'ancien agrégat.
        d.addCallback(_delete)
        d.addCallback(lambda res: event_id_list)
        return d

    d.addCallback(_merge)
    return d
