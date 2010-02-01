# -*- coding: utf-8 -*-
"""Suite de tests pour la classe 'Topology'"""
from datetime import datetime
import unittest
import nose

from vigilo.models.session import DBSession
from vigilo.models import Host, LowLevelService, Dependency
from vigilo.models import Event, CorrEvent, StateName

from vigilo.corr.topology import Topology
from utils import setup_db, teardown_db
    
class TestTopologyFunctions(unittest.TestCase):
    """Test des méthodes de la classe 'Topology'"""
    
    def add_services(self):
        """Création de 5 couples host/service"""
        self.host1 = Host(
            name = u'messagerie',
            checkhostcmd = u'check11',
            snmpcommunity = u'com11',
            hosttpl = u'tpl11',
            mainip = u'192.168.0.11',
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
            mainip = u'192.168.0.26',
            snmpport = 26,
            weight = 42,
        )
        DBSession.add(self.host2)
        DBSession.flush()
        
        self.service1 = LowLevelService(
            servicename = u'Processes',
            host = self.host1,
            command = u'halt',
            op_dep = u'&',
            weight = 42,
        )
        DBSession.add(self.service1)
        DBSession.flush()
        
        self.service2 = LowLevelService(
            servicename = u'CPU',
            host = self.host1,
            command = u'halt',
            op_dep = u'&',
            weight = 42,
        )
        DBSession.add(self.service2)
        DBSession.flush()
        
        self.service3 = LowLevelService(
            servicename = u'RAM',
            host = self.host1,
            command = u'halt',
            op_dep = u'&',
            weight = 42,
        )
        DBSession.add(self.service3)
        DBSession.flush()
        
        self.service4 = LowLevelService(
            servicename = u'Interface eth0',
            host = self.host1,
            command = u'halt',
            op_dep = u'&',
            weight = 42,
        )
        DBSession.add(self.service4)
        DBSession.flush()
        
        self.service5 = LowLevelService(
            servicename = u'Interface eth1',
            host = self.host2,
            command = u'halt',
            op_dep = u'&',
            weight = 42,
        )
        DBSession.add(self.service5)
        DBSession.flush()

    def add_dependencies(self):
        """
        Ajout de quelques dépendances entre services de bas 
        niveau dans la BDD, préalable à certains des test.
        """
        self.dependency1 = Dependency(
            idsupitem1 = self.service1.idservice,
            idsupitem2 = self.service2.idservice
        )
        DBSession.add(self.dependency1)
        DBSession.flush()
        
        self.dependency2 = Dependency(
            idsupitem1 = self.service1.idservice,
            idsupitem2 = self.service3.idservice
        )
        DBSession.add(self.dependency2)
        DBSession.flush()
            
        self.dependency3 = Dependency(
            idsupitem1 = self.service2.idservice,
            idsupitem2 = self.service4.idservice
        )
        DBSession.add(self.dependency3)
        DBSession.flush()
            
        self.dependency4 = Dependency(
            idsupitem1 = self.service3.idservice,
            idsupitem2 = self.service4.idservice
        )
        DBSession.add(self.dependency4)
        DBSession.flush()
            
        self.dependency5 = Dependency(
            idsupitem1 = self.service4.idservice,
            idsupitem2 = self.service5.idservice
        )
        DBSession.add(self.dependency5)
        DBSession.flush()
    
    def add_events_and_aggregates(self):
        """
        Ajout de quelques événements associés à des services de
        bas niveau dans la BDD, ainsi que de quelques agrégats.
        """
        self.event1 = Event(
            idsupitem = self.service3.idservice, 
            current_state = 2,
            message = 'WARNING: RAM is overloaded'
        )
        DBSession.add(self.event1)
        DBSession.flush()
        
        self.event2 = Event(
            idsupitem = self.service4.idservice, 
            current_state = 2,
            message = 'WARNING: eth0 is down'
        )
        DBSession.add(self.event2)
        DBSession.flush()
        
        self.events_aggregate1 = CorrEvent( 
            idcause = self.event1.idevent,
            impact = 1,
            priority = 1,
            trouble_ticket = u'azerty1234',
            status = u'None',
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
            status = u'None',
            occurrence = 1,
            timestamp_active = datetime.now(),
        )
        self.events_aggregate2.events.append(self.event2)
        DBSession.add(self.events_aggregate2)
        DBSession.flush()
        
        # Ajout des noms d'états dans la BDD
        DBSession.add(StateName(
            statename = u'OK',
            order = 0))
        DBSession.add(StateName(
            statename = u'UNKNOWN',
            order = 1))
        DBSession.add( StateName(
            statename = u'WARNING',
            order = 2))
        DBSession.add(StateName(
            statename = u'CRITICAL',
            order = 3))
        DBSession.add(StateName(
            statename = u'UP',
            order = 0))
        DBSession.add(StateName(
            statename = u'UNREACHABLE',
            order = 1))
        DBSession.add(StateName(
            statename = u'DOWN',
            order = 3))
        DBSession.flush()
    
    def setUp(self):
        """Initialisation de la BDD préalable à chacun des tests"""
        setup_db()
        
        # Création de 5 couples host/service
        self.add_services()
        
        # On ajoute quelques dépendances entre 
        # les services de bas niveau dans la BDD.
        self.add_dependencies()
        
    def tearDown(self):
        """Nettoyage de la BDD à la fin de chaque test"""
        DBSession.expunge_all()
        DBSession.rollback()
        DBSession.flush()
        teardown_db()

    def test_instanciation(self):
        """Test de création d'une instance de la classe"""
        
        # On instancie la classe topology.
        topology = Topology()
        
        # On vérifie que les noeuds correspondent bien
        # à la liste des services insérés dans la BDD.
        nodes = topology.nodes()
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
        edges = topology.edges()
        edges.sort()
        edge_list = [(self.service2.idservice, self.service1.idservice),
                    (self.service3.idservice, self.service1.idservice),
                    (self.service4.idservice, self.service2.idservice),
                    (self.service4.idservice, self.service3.idservice),
                    (self.service5.idservice, self.service4.idservice)]
        edge_list.sort()
        self.assertEqual(edges, edge_list)
        
    def test_first_predecessors_aggregates(self):  
        """
        Test de récupération des premiers agrégats dont dépend une alerte.
        """ 
        
        # On instancie la classe topology.
        topology = Topology()
        
        # On ajoute quelques événements et agrégats
        self.add_events_and_aggregates()
        
        # On récupère les aggrégats dont dépend le service 1
        aggregates = topology.get_first_predecessors_aggregates(
                                                    self.service1.idservice)
        aggregates_id = []
        for aggregate in aggregates:
            aggregates_id.append(aggregate.idcorrevent)
        aggregates_id.sort()
        aggregate_list = [self.events_aggregate1.idcorrevent,
                          self.events_aggregate2.idcorrevent]
        aggregate_list.sort()
        # On vérifie que le service 1 dépend bien des agrégats 1 et 2
        self.assertEqual(aggregates_id, aggregate_list)
        
        # On récupère les aggrégats dont dépend le service 2
        aggregates = topology.get_first_predecessors_aggregates(
                                                    self.service2.idservice)
        aggregates_id = []
        for aggregate in aggregates:
            aggregates_id.append(aggregate.idcorrevent)
        aggregates_id.sort()
        # On vérifie que le service 2 dépend bien de l'agrégat 2
        self.assertEqual(aggregates_id, [self.events_aggregate2.idcorrevent])
    
    def test_first_successors_aggregates(self):  
        """
        Test de récupération des premiers agrégats dépendant d'une alerte.
        """ 
        
        # On instancie la classe topology.
        topology = Topology()
        
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
            message = 'WARNING: Processes are not responding'
        )
        DBSession.add(self.event3)
        DBSession.flush()
        
        self.events_aggregate3 = CorrEvent( 
            idcause = self.event3.idevent,
            impact = 1,
            priority = 1,
            trouble_ticket = u'azerty1234',
            status = u'None',
            occurrence = 1,
            timestamp_active = datetime.now(),
        )
        self.events_aggregate3.events.append(self.event3)
        DBSession.add(self.events_aggregate3)
        DBSession.flush()
        
        # On récupère les aggrégats causés par le service 5
        aggregates = topology.get_first_successors_aggregates(
                                                    self.service5.idservice)
        aggregates_id = []
        for aggregate in aggregates:
            aggregates_id.append(aggregate.idcorrevent)
        aggregates_id.sort()
        # On vérifie que le service 5 n'a causé aucun agrégat directement.
        self.assertEqual(aggregates_id, [])
        
        # On récupère les aggrégats causés par le service 4
        aggregates = topology.get_first_successors_aggregates(
                                                    self.service4.idservice)
        aggregates_id = []
        for aggregate in aggregates:
            aggregates_id.append(aggregate.idcorrevent)
        aggregates_id.sort()
        # On vérifie que le service 4 a bien causé l'agrégat 1
        # (Et uniquement l'agrégat 1).
        self.assertEqual(aggregates_id, [self.events_aggregate1.idcorrevent])
    
if __name__ == "__main__": 
    nose.main()
