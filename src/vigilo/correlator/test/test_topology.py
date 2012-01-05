# -*- coding: utf-8 -*-
# pylint: disable-msg=C0111,W0212,R0904
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""Suite de tests pour la classe 'Topology'"""
from datetime import datetime
import unittest

from nose.twistedtools import reactor, deferred
from twisted.internet import defer

from vigilo.models.session import DBSession
from vigilo.models.tables import Host, LowLevelService, \
                                    Dependency, DependencyGroup
from vigilo.models.tables import Event, CorrEvent

from vigilo.correlator.topology import Topology
from vigilo.correlator.db_thread import DummyDatabaseWrapper
import helpers

class TopologyTestHelpers(object):
    @deferred(timeout=30)
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

    @deferred(timeout=30)
    def tearDown(self):
        """Nettoyage de la BDD à la fin de chaque test"""
        self.context_factory.reset()
        helpers.teardown_db()
        return defer.succeed(None)

    def add_services(self):
        """Création de 5 couples host/service"""
        self.host1 = Host(
            name = u'messagerie',
            checkhostcmd = u'check11',
            snmpcommunity = u'com11',
            hosttpl = u'tpl11',
            address = u'192.168.0.11',
            snmpport = 11,
            weight = 42,
        )
        DBSession.add(self.host1)
        DBSession.flush()

        self.host2 = Host(
            name = u'firewall',
            checkhostcmd = u'check26',
            snmpcommunity = u'com26',
            hosttpl = u'tpl26',
            address = u'192.168.0.26',
            snmpport = 26,
            weight = 42,
        )
        DBSession.add(self.host2)
        DBSession.flush()

        self.service1 = LowLevelService(
            servicename = u'Processes',
            host = self.host1,
            command = u'halt',
            weight = 42,
        )
        DBSession.add(self.service1)
        DBSession.flush()

        self.service2 = LowLevelService(
            servicename = u'CPU',
            host = self.host1,
            command = u'halt',
            weight = 42,
        )
        DBSession.add(self.service2)
        DBSession.flush()

        self.service3 = LowLevelService(
            servicename = u'RAM',
            host = self.host1,
            command = u'halt',
            weight = 42,
        )
        DBSession.add(self.service3)
        DBSession.flush()

        self.service4 = LowLevelService(
            servicename = u'Interface eth0',
            host = self.host1,
            command = u'halt',
            weight = 42,
        )
        DBSession.add(self.service4)
        DBSession.flush()

        self.service5 = LowLevelService(
            servicename = u'Interface eth1',
            host = self.host2,
            command = u'halt',
            weight = 42,
        )
        DBSession.add(self.service5)
        DBSession.flush()

    def add_dependencies(self):
        """
        Ajout de quelques dépendances entre services de bas
        niveau dans la BDD, préalable à certains des test.
        """
        dep_group1 = DependencyGroup(
            dependent=self.service1,
            operator=u'|',
            role=u'topology',
        )
        dep_group2 = DependencyGroup(
            dependent=self.service2,
            operator=u'|',
            role=u'topology',
        )
        dep_group3 = DependencyGroup(
            dependent=self.service3,
            operator=u'|',
            role=u'topology',
        )
        dep_group4 = DependencyGroup(
            dependent=self.service4,
            operator=u'|',
            role=u'topology',
        )
        DBSession.add(dep_group1)
        DBSession.add(dep_group2)
        DBSession.add(dep_group3)
        DBSession.add(dep_group4)
        DBSession.flush()

        self.dependency1 = Dependency(group=dep_group1, supitem=self.service2)
        DBSession.add(self.dependency1)
        DBSession.flush()

        self.dependency2 = Dependency(group=dep_group1, supitem=self.service3)
        DBSession.add(self.dependency2)
        DBSession.flush()

        self.dependency3 = Dependency(group=dep_group2, supitem=self.service4)
        DBSession.add(self.dependency3)
        DBSession.flush()

        self.dependency4 = Dependency(group=dep_group3, supitem=self.service4)
        DBSession.add(self.dependency4)
        DBSession.flush()

        self.dependency5 = Dependency(group=dep_group4, supitem=self.service5)
        DBSession.add(self.dependency5)
        DBSession.flush()

class TestTopologyFunctions(TopologyTestHelpers, unittest.TestCase):
    """Test des méthodes de la classe 'Topology'"""
    def add_events_and_aggregates(self):
        """
        Ajout de quelques événements associés à des services de
        bas niveau dans la BDD, ainsi que de quelques agrégats.
        """
        self.event1 = Event(
            idsupitem = self.service3.idservice,
            current_state = 2,
            message = 'WARNING: RAM is overloaded',
            timestamp = datetime.now(),
        )
        DBSession.add(self.event1)
        DBSession.flush()

        self.event2 = Event(
            idsupitem = self.service4.idservice,
            current_state = 2,
            message = 'WARNING: eth0 is down',
            timestamp = datetime.now(),
        )
        DBSession.add(self.event2)
        DBSession.flush()

        self.events_aggregate1 = CorrEvent(
            idcause = self.event1.idevent,
            impact = 1,
            priority = 1,
            trouble_ticket = u'azerty1234',
            ack = CorrEvent.ACK_NONE,
            occurrence = 1,
            timestamp_active = datetime.now(),
        )
        self.events_aggregate1.events.append(self.event1)
        DBSession.add(self.events_aggregate1)
        DBSession.flush()

        self.events_aggregate2 = CorrEvent(
            idcause = self.event2.idevent,
            impact = 1,
            priority = 1,
            trouble_ticket = u'azerty1234',
            ack = CorrEvent.ACK_NONE,
            occurrence = 1,
            timestamp_active = datetime.now(),
        )
        self.events_aggregate2.events.append(self.event2)
        DBSession.add(self.events_aggregate2)
        DBSession.flush()

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

    @deferred(timeout=30)
    @defer.inlineCallbacks
    def test_first_predecessors_aggregates(self):
        """Récupération des premiers agrégats dont dépend une alerte brute"""
        # On ajoute quelques événements et agrégats
        self.add_events_and_aggregates()
        ctx = self.context_factory(141, defer=True)
        ctx._connection._must_defer = False

        # On récupère les aggrégats dont dépend le service 1
        print "First step"
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
        print "Second step"
        aggregates = yield self.topology.get_first_predecessors_aggregates(
            ctx,
            self.database,
            self.service2.idservice
        )
        aggregates.sort()
        # On vérifie que le service 2 dépend bien de l'agrégat 2
        self.assertEqual(aggregates, [self.events_aggregate2.idcorrevent])

    @deferred(timeout=30)
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
        self.event3 = Event(
            idsupitem = self.service1.idservice,
            current_state = 2,
            message = 'WARNING: Processes are not responding',
            timestamp = datetime.now(),
        )
        DBSession.add(self.event3)
        DBSession.flush()

        self.events_aggregate3 = CorrEvent(
            idcause = self.event3.idevent,
            impact = 1,
            priority = 1,
            trouble_ticket = u'azerty1234',
            ack = CorrEvent.ACK_NONE,
            occurrence = 1,
            timestamp_active = datetime.now(),
        )
        self.events_aggregate3.events.append(self.event3)
        DBSession.add(self.events_aggregate3)
        DBSession.flush()

        # On récupère les aggrégats causés par le service 5
        ctx = self.context_factory(142, defer=True)
        ctx._connection._must_defer = False
        print "First step"
        aggregates = yield self.topology.get_first_successors_aggregates(
            ctx,
            self.database,
            self.service5.idservice
        )
        aggregates.sort()
        # On vérifie que le service 5 n'a causé aucun agrégat directement.
        self.assertEqual(aggregates, [])

        # On récupère les aggrégats causés par le service 4
        print "Second step"
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
        self.event1 = Event(
            idsupitem = self.service3.idservice,
            current_state = 2,
            message = 'WARNING: RAM is overloaded',
            timestamp = datetime.now(),
        )
        DBSession.add(self.event1)
        DBSession.flush()

        self.events_aggregate1 = CorrEvent(
            idcause = self.event1.idevent,
            impact = 1,
            priority = 1,
            trouble_ticket = u'azerty1234',
            ack = CorrEvent.ACK_NONE,
            occurrence = 1,
            timestamp_active = datetime.now(),
        )
        self.events_aggregate1.events.append(self.event1)
        DBSession.add(self.events_aggregate1)
        DBSession.flush()

    @deferred(timeout=30)
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
        self.assertEquals([], aggregates)
