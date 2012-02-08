# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# pylint: disable-msg=C0111,W0212,R0904
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Test du module publish_messages.
"""

import unittest
from datetime import datetime
from time import mktime

from vigilo.correlator.publish_messages import MessagePublisher

from vigilo.models.session import DBSession
from vigilo.models.demo import functions
from vigilo.models.tables import Host, HighLevelService, LowLevelService
from vigilo.models.tables import State, StateName

from mock import Mock

from vigilo.correlator.test import helpers



class MessagePublisherTestCase(unittest.TestCase):
    """Suite de tests du module publish_messages"""


    def setUp(self):
        """Initialisation d'une réplique du RuleDispatcher."""
        self.mp = MessagePublisher(
                helpers.settings['correlator']['nagios_hls_host'], {})
        self.mp.sendMessage = Mock()

        # Initialisation de la BDD
        helpers.setup_db()

        # Ajout des noms d'états dans la BDD
        helpers.populate_statename()

        # Ajout d'un hôte dans la BDD
        self.host1 = functions.add_host(u'host1.example.com')

        # Ajout d'un service de haut niveau dans la BDD
        self.hls1 = functions.add_highlevelservice(u'Connexion')

        # Ajout d'un service de bas niveau dans la BDD
        self.lls1 = functions.add_lowlevelservice(self.host1, u'Processes')

        # Création d'un timestamp à partir de l'heure actuelle
        self.timestamp = datetime.now()
        self.int_timestamp = int(mktime(self.timestamp.timetuple()))


    def tearDown(self):
        helpers.teardown_db()


    def test_publish_aggregate(self):
        """Publication d'alertes à ajouter à des évènements corrélés"""
        self.mp.publish_aggregate([1, 2], [1, 2, 3, 4])
        print self.mp.sendMessage.call_args
        self.assertEqual(self.mp.sendMessage.call_args[0][0],
                {'aggregates': [1, 2], 'alerts': [1, 2, 3, 4], 'type': 'aggr'})


    def test_delete_published_aggregates(self):
        """Publication d'une liste d'évènements corrélés à supprimer"""
        self.mp.delete_published_aggregates([1, 2])
        print self.mp.sendMessage.call_args
        self.assertEqual(self.mp.sendMessage.call_args[0][0],
                {'aggregates': [1, 2], 'type': 'delaggr'})


    def test_publish_state_host(self):
        """Publication de l'état d'un hôte"""
        # Ajout de l'état du host1 dans la BDD
        state1 = functions.add_host_state(
                    self.host1, u'UNREACHABLE', 'UNREACHABLE: Host1',
                    self.timestamp)

        info_dictionary = {"host": "host1.example.com",
                           "service": None,
                           "timestamp": state1.timestamp,
                           "state": StateName.value_to_statename(state1.state),
                           "message": state1.message}

        # On publie l'état du host1 sur le bus
        self.mp.publish_state(info_dictionary)

        message = {'type': 'state',
                   'timestamp': self.int_timestamp,
                   'host': 'host1.example.com',
                   'message': 'UNREACHABLE: Host1',
                   'state': u'UNREACHABLE'
                   }

        # On vérifie que le message publié sur le bus concernant
        # l'état du host1 est bien celui attendu.
        self.assertEqual(self.mp.sendMessage.call_args[0][0], message)

    def test_publish_state_hls(self):
        # Ajout de l'état du hls1 dans la BDD
        state2 = functions.add_svc_state(
                    self.hls1, u'UNKNOWN',
                    'UNKNOWN: Connection is in an unknown state',
                    self.timestamp)

        info_dictionary = {"host":
                            helpers.settings['correlator']['nagios_hls_host'],
                           "service": "Connexion",
                           "timestamp": state2.timestamp,
                           "state": StateName.value_to_statename(state2.state),
                           "message": state2.message}

        # On publie l'état du hls1 sur le bus
        self.mp.publish_state(info_dictionary)

        message = {'type': 'state',
                   'timestamp': self.int_timestamp,
                   'host': helpers.settings['correlator']['nagios_hls_host'],
                   'service': 'Connexion',
                   'state': u'UNKNOWN',
                   'message': 'UNKNOWN: Connection is in an unknown state',
                   }

        # On vérifie que le message publié sur le bus concernant
        # l'état du hls1 est bien celui attendu.
        self.assertEqual(self.mp.sendMessage.call_args[0][0], message)

    def test_publish_state_lls(self):
        # Ajout de l'état du lls1 dans la BDD
        state3 = functions.add_svc_state(
                    self.lls1, u'UNKNOWN',
                    'UNKNOWN: Processes are in an unknown state',
                    self.timestamp)

        info_dictionary = {"host": "host1.example.com",
                           "service": "Processes",
                           "timestamp": state3.timestamp,
                           "state": StateName.value_to_statename(state3.state),
                           "message": state3.message}

        # On publie l'état du lls1 sur le bus
        self.mp.publish_state(info_dictionary)

        message = {'type': 'state',
                   'host': 'host1.example.com',
                   'service': 'Processes',
                   'timestamp': self.int_timestamp,
                   'state': u'UNKNOWN',
                   'message': 'UNKNOWN: Processes are in an unknown state',
                   }

        # On vérifie que le message publié sur le bus concernant
        # l'état du lls1 est bien celui attendu.
        self.assertEqual(self.mp.sendMessage.call_args[0][0], message)

