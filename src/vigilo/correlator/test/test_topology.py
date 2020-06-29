# -*- coding: utf-8 -*-
# Copyright (C) 2006-2020 CS GROUP – France
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""Suite de tests pour la classe 'Topology'"""

# pylint: disable-msg=C0111,W0212,R0904,W0201
# - C0111: Missing docstring
# - W0212: Access to a protected member of a client class
# - R0904: Too many public methods
# - W0201: Attribute defined outside __init__

from __future__ import print_function
import unittest

from nose.twistedtools import reactor  # pylint: disable-msg=W0611
from nose.twistedtools import deferred

from twisted.internet import defer

from vigilo.models.session import DBSession
from vigilo.models.demo import functions

from vigilo.correlator.topology import Topology
from vigilo.correlator.db_thread import DummyDatabaseWrapper
from vigilo.correlator.test import helpers

class TopologyTestHelpers(object):
    @deferred(timeout=60)
    def setUp(self):
        """Initialisation de la BDD préalable à chacun des tests"""
        helpers.setup_db()
        helpers.populate_statename()

        # Création de 5 couples host/service
        self.add_services()

        # On ajoute quelques dépendances entre
        # les services de bas niveau dans la BDD.
        self.add_dependencies()

        # On prépare la topology.
        self.topology = Topology()
        self.topology.generate()
        self.context_factory = helpers.ContextStubFactory()
        self.database = DummyDatabaseWrapper(True, async=False)
        return defer.succeed(None)

    @deferred(timeout=60)
    def tearDown(self):
        """Nettoyage de la BDD à la fin de chaque test"""
        self.context_factory.reset()
        helpers.teardown_db()
        return defer.succeed(None)

    def add_services(self):
        """Création de 5 couples host/service"""
        self.host1 = functions.add_host(u'messagerie')
        self.host2 = functions.add_host(u'firewall')

        self.service1 = functions.add_lowlevelservice(self.host1, u'Processes')
        self.service2 = functions.add_lowlevelservice(self.host1, u'CPU')
        self.service3 = functions.add_lowlevelservice(self.host1, u'RAM')
        self.service4 = functions.add_lowlevelservice(self.host1, u'Interface eth0')
        self.service5 = functions.add_lowlevelservice(self.host2, u'Interface eth1')

    def add_dependencies(self):
        """
        Ajout de quelques dépendances entre services de bas
        niveau dans la BDD, préalable à certains des test.
        """
        dep_group1 = functions.add_dependency_group(None, self.service1, u'topology', u'|')
        dep_group2 = functions.add_dependency_group(None, self.service2, u'topology', u'|')
        dep_group3 = functions.add_dependency_group(None, self.service3, u'topology', u'|')
        dep_group4 = functions.add_dependency_group(None, self.service4, u'topology', u'|')

        self.dependency1 = functions.add_dependency(dep_group1, self.service2, 1)
        self.dependency2 = functions.add_dependency(dep_group1, self.service3, 1)
        self.dependency3 = functions.add_dependency(dep_group2, self.service4, 1)
        self.dependency4 = functions.add_dependency(dep_group3, self.service4, 1)
        self.dependency5 = functions.add_dependency(dep_group4, self.service5, 1)

class TestTopologyFunctions(TopologyTestHelpers, unittest.TestCase):
    """Test des méthodes de la classe 'Topology'"""
    def add_events_and_aggregates(self):
        """
        Ajout de quelques événements associés à des services de
        bas niveau dans la BDD, ainsi que de quelques agrégats.
        """
        self.event1 = functions.add_event(self.service3, u'WARNING', 'WARNING: RAM is overloaded')
        self.event2 = functions.add_event(self.service4, u'WARNING', 'WARNING: eth0 is down')
        self.events_aggregate1 = functions.add_correvent([self.event1])
        self.events_aggregate2 = functions.add_correvent([self.event2])

    def test_instanciation(self):
        """Instanciation de la classe 'Topology'"""
        # On vérifie que les noeuds correspondent bien
        # à la liste des services insérés dans la BDD.
        nodes = self.topology.nodes()
        nodes.sort()
        node_list = [self.service1.idservice,
                    self.service2.idservice,
                    self.service3.idservice,
                    self.service4.idservice,
                    self.service5.idservice]
        node_list.sort()
        self.assertEqual(nodes, node_list)

        # On vérifie que les dépendances correspondent
        # bien à la liste celles de la BDD.
        edges = self.topology.edges()
        edges.sort()
        edge_list = [(self.service2.idservice, self.service1.idservice),
                    (self.service3.idservice, self.service1.idservice),
                    (self.service4.idservice, self.service2.idservice),
                    (self.service4.idservice, self.service3.idservice),
                    (self.service5.idservice, self.service4.idservice)]
        edge_list.sort()
        self.assertEqual(edges, edge_list)

    @deferred(timeout=60)
    @defer.inlineCallbacks
    def test_first_predecessors_aggregates(self):
        """Récupération des premiers agrégats dont dépend une alerte brute"""
        # On ajoute quelques événements et agrégats
        self.add_events_and_aggregates()
        ctx = self.context_factory(141, defer=True)
        ctx._connection._must_defer = False

        # On récupère les aggrégats dont dépend le service 1
        print("First step")
        aggregates = yield self.topology.get_first_predecessors_aggregates(
            ctx,
            self.database,
            self.service1.idservice
        )
        aggregates.sort()
        aggregate_list = [self.events_aggregate1.idcorrevent,
                          self.events_aggregate2.idcorrevent]
        aggregate_list.sort()
        # On vérifie que le service 1 dépend bien des agrégats 1 et 2
        self.assertEqual(aggregates, aggregate_list)

        # On récupère les aggrégats dont dépend le service 2
        print("Second step")
        aggregates = yield self.topology.get_first_predecessors_aggregates(
            ctx,
            self.database,
            self.service2.idservice
        )
        aggregates.sort()
        # On vérifie que le service 2 dépend bien de l'agrégat 2
        self.assertEqual(aggregates, [self.events_aggregate2.idcorrevent])

    @deferred(timeout=60)
    @defer.inlineCallbacks
    def test_first_successors_aggregates(self):
        """Récupération des premiers agrégats dépendant d'une alerte brute"""
        # On ajoute quelques événements et agrégats
        self.add_events_and_aggregates()

        # On supprime un agrégat
        DBSession.delete(self.events_aggregate2)
        DBSession.flush()

        # On ajoute un événement et un nouvel
        # agrégat dont cet événement est la cause.
        self.event3 = functions.add_event(self.service1, u'WARNING', 'WARNING: Processes are not responding')
        self.events_aggregate3 = functions.add_correvent([self.event3])

        # On récupère les aggrégats causés par le service 5
        ctx = self.context_factory(142, defer=True)
        ctx._connection._must_defer = False
        print("First step")
        aggregates = yield self.topology.get_first_successors_aggregates(
            ctx,
            self.database,
            self.service5.idservice
        )
        aggregates.sort()
        # On vérifie que le service 5 n'a causé aucun agrégat directement.
        self.assertEqual(aggregates, [])

        # On récupère les aggrégats causés par le service 4
        print("Second step")
        aggregates = yield self.topology.get_first_successors_aggregates(
            ctx,
            self.database,
            self.service4.idservice
        )
        aggregates.sort()
        # On vérifie que le service 4 a bien causé l'agrégat 1
        # (Et uniquement l'agrégat 1).
        self.assertEqual(aggregates, [self.events_aggregate1.idcorrevent])

class TestPredecessorsAliveness(TopologyTestHelpers, unittest.TestCase):
    """
    Teste la détection de chemins "vivants" dans la topologie.
    """
    def add_events_and_aggregates(self):
        """
        Ajout de quelques événements associés à des services de
        bas niveau dans la BDD, ainsi que de quelques agrégats.
        """
        self.event1 = functions.add_event(self.service3, u'WARNING', 'WARNING: RAM is overloaded')
        self.events_aggregate1 = functions.add_correvent([self.event1])

    @deferred(timeout=60)
    @defer.inlineCallbacks
    def test_first_predecessors_aggregates(self):
        """Pas d'agrégats prédecesseurs s'il existe un chemin "vivant"."""
        # On ajoute quelques événements et agrégats
        self.add_events_and_aggregates()

        # On récupère les aggrégats dont dépend le service 1
        ctx = self.context_factory(143)
        ctx._connection._must_defer = False
        aggregates = yield self.topology.get_first_predecessors_aggregates(
            ctx,
            self.database,
            self.service1.idservice
        )
        self.assertEqual([], aggregates)
