# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2020 CS GROUP – France
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Prend en charge les messages concernant les tickets d'incidents.
"""

from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound
from sqlalchemy.exc import IntegrityError, InvalidRequestError

from vigilo.models.session import DBSession
from vigilo.models.tables import CorrEvent, EventHistory

from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)

from vigilo.common.gettext import translate
_ = translate(__name__)


def handle_ticket(info_dictionary):
    """
    Met à jour l'historique d'un évènement corrélé dans la base de
    données après la réception d'un message sur le bus indiquant
    la modification du ticket d'incident qui lui est associé.

    @param info_dictionary: Dictionnaire contenant les
    informations extraites du message reçu par le rule dispatcher.
    @type info_dictionary: C{dictionary}

    Cette fonction permet de satisfaire l'exigence VIGILO_EXIG_VIGILO_BAC_0120
    """
    LOGGER.debug(_(u'handle_ticket: Trouble ticket message received. '
                 'Timestamp = %(timestamp)r. Impacted HLS = %(hls)r. '
                 'Ticket id = %(ticket_id)r. acknowledgement_status = '
                 '%(ack_status)r. Message = %(message)r.'),
                 {
                    'timestamp': info_dictionary["timestamp"],
                    'hls': info_dictionary["highlevel"],
                    'ticket_id': info_dictionary["ticket_id"],
                    'ack_status': info_dictionary["acknowledgement_status"],
                    'message': info_dictionary["message"],
                 })

    # On cherche dans la BDD l'évènement
    # corrélé associé à ce ticket d'incident.
    try:
        correvent = DBSession.query(
                    CorrEvent
                ).filter(
                    CorrEvent.trouble_ticket == info_dictionary["ticket_id"]
                ).one()
    except NoResultFound:
        # Si aucun évènement n'est trouvé on loggue une erreur.
        LOGGER.error(_(u'handle_ticket: No matching trouble ticket found : %r'),
                       info_dictionary["ticket_id"])
        return

    except MultipleResultsFound:
        # Si plusieurs évènements sont trouvés on loggue une erreur.
        LOGGER.error(_(u'handle_ticket: Several events seem to be associated '
                       'with this ticket : %r'), info_dictionary["ticket_id"])
        return
    LOGGER.debug(_(u'handle_ticket: The event %(event_id)r is '
                   'associated with the given ticket (%(ticket_id)r)'), {
                        'event_id': correvent.idcorrevent,
                        'ticket_id': info_dictionary["ticket_id"],
                    })

    # Mise à jour de l'historique de l'évènement corrélé :
    history = EventHistory()
    history.type_action = u'Ticket change notification'
    history.idevent = correvent.idcorrevent
    history.value = info_dictionary['ticket_id']
    history.text = '%r;%r;%r' % (info_dictionary['acknowledgement_status'],
                                 info_dictionary['message'],
                                 info_dictionary['highlevel'])
    history.timestamp = info_dictionary['timestamp']
    history.username = None

    try:
        DBSession.add(history)
        DBSession.flush()

    except (IntegrityError, InvalidRequestError):
        LOGGER.exception(_(u'handle_ticket: Got exception while updating '
                            'event %r history'), correvent.idcorrevent)

    else:
        LOGGER.debug(_(u'handle_ticket: Event %r history updated '
                        'successfully.'), correvent.idcorrevent)

