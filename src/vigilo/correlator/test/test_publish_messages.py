# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# pylint: disable-msg=C0111,W0212,R0904
# Copyright (C) 2006-2016 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Test du module publish_messages.
"""

from __future__ import print_function
import unittest
from datetime import datetime
from time import mktime

from mock import Mock

from vigilo.models.demo import functions
from vigilo.correlator.publish_messages import MessagePublisher

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
        print(self.mp.sendMessage.call_args)
        self.assertEqual(self.mp.sendMessage.call_args[0][0],
                {'aggregates': [1, 2], 'alerts': [1, 2, 3, 4], 'type': 'aggr'})


    def test_delete_published_aggregates(self):
        """Publication d'une liste d'évènements corrélés à supprimer"""
        self.mp.delete_published_aggregates([1, 2])
        print(self.mp.sendMessage.call_args)
        self.assertEqual(self.mp.sendMessage.call_args[0][0],
                {'aggregates': [1, 2], 'type': 'delaggr'})
