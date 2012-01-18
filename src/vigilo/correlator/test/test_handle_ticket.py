# -*- coding: utf-8 -*-
# pylint: disable-msg=C0111,W0212,R0904
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""Suite de tests pour le module 'handle_ticket'"""
from datetime import datetime
import unittest

from vigilo.models.session import DBSession
from vigilo.models.demo import functions
from vigilo.models.tables import Host, Event, EventHistory, CorrEvent, StateName

from vigilo.correlator.handle_ticket import handle_ticket
import helpers

class TestHandleTicket(unittest.TestCase):
    """Test des méthodes du module 'handle_ticket'"""

    def add_data(self):
        """Ajout des données dans la base avant les tests"""
        helpers.populate_statename()
        self.host = functions.add_host(u'messagerie')
        self.event = functions.add_event(self.host, u'WARNING', 'WARNING')
        self.events_aggregate = functions.add_correvent([self.event])
        self.events_aggregate.trouble_ticket = u'azerty1234'
        DBSession.add(self.events_aggregate)
        DBSession.flush()

    def setUp(self):
        """Initialisation de la BDD préalable à chacun des tests"""
        helpers.setup_db()
        self.add_data()

    def tearDown(self):
        """Nettoyage de la BDD à la fin de chaque test"""
        helpers.teardown_db()

    def test_message_reception(self):
        """
        Traitement d'un message de notification d'un ticket d'incident.
        """
        # On vérifie que la table EventHistory est bien vide.
        self.assertEqual(DBSession.query(EventHistory.idhistory).count(), 0)

        # On initialise les données du message.
        info_dictionary = {
            'timestamp': datetime.now(),
            'impacted_HLS': '',
            'ticket_id': u'azerty1234',
            'acknowledgement_status': 'foo',
            'message': 'bar',
        }

        # On traite le message.
        handle_ticket(info_dictionary)

        # On vérifie que la table EventHistory
        # contient bien un enregistrement.
        self.assertEqual(DBSession.query(EventHistory.idhistory).count(), 1)

        # On vérifie que les données de cet
        # enregistrement sont bien celles attendues.
        history = DBSession.query(EventHistory).one()
        self.assertEqual(history.type_action, u'Ticket change notification')
        self.assertEqual(history.idevent, self.events_aggregate.idcorrevent)
        self.assertEqual(history.text, '%r;%r;%r' %
                            (info_dictionary['acknowledgement_status'],
                             info_dictionary['message'],
                             info_dictionary['impacted_HLS']))
        self.assertEqual(history.timestamp, info_dictionary['timestamp'])
        self.assertFalse(history.username)
