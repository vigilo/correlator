# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""
Test de la fonction merge_aggregates.
"""

from datetime import datetime
import unittest

from vigilo.corr.db_insertion import merge_aggregates
from utils import setup_db, teardown_db

from vigilo.models.configure import DBSession
from vigilo.models import Event, CorrEvent
from vigilo.models import LowLevelService, Host

def create_topology_and_events():
    """
    Création de 4 couples host/service, 
    4 événéments et 2 agrégats dans la BDD.
    """   
    # On crée 4 couples host/service.
    host1 = Host(
        name = u'messagerie',
        checkhostcmd = u'check11',
        snmpcommunity = u'com11',
        hosttpl = u'tpl11',
        mainip = u'192.168.0.11',
        snmpport = 11,
        weight = 42,
    )
    DBSession.add(host1)
    DBSession.flush()
    
    service1 = LowLevelService(
        servicename = u'Processes',
        host = host1,
        command = u'halt',
        op_dep = u'&',
        weight = 42,
    )
    DBSession.add(service1)
    DBSession.flush()

    service2 = LowLevelService(
        servicename = u'CPU',
        host = host1,
        command = u'halt',
        op_dep = u'&',
        weight = 42,
    )
    DBSession.add(service2)
    DBSession.flush()
        
    service3 = LowLevelService(
        servicename = u'RAM',
        host = host1,
        command = u'halt',
        op_dep = u'&',
        weight = 42,
    )
    DBSession.add(service3)
    DBSession.flush()
        
    service4 = LowLevelService(
        servicename = u'Interface eth0',
        host = host1,
        command = u'halt',
        op_dep = u'&',
        weight = 42,
    )
    DBSession.add(service4)
    DBSession.flush()
        
    # On ajoute 4 événements et 2 agrégats dans la BDD.
    event1 = Event(
        supitem = service1,
        current_state = 2,
        message = 'WARNING: Processes are not responding'
    )
    DBSession.add(event1)
    DBSession.flush()
        
    event2 = Event(
        supitem = service2,
        current_state = 2,
        message = 'WARNING: CPU is overloaded'
    )
    DBSession.add(event2)
    DBSession.flush()
        
    event3 = Event(
        supitem = service3,
        current_state = 2,
        message = 'WARNING: RAM is overloaded'
    )
        
    DBSession.add(event3)
    DBSession.flush()
        
    event4 = Event(
        supitem = service4,
        current_state = 2,
        message = 'WARNING: eth0 is down'
    )
    
    DBSession.add(event4)
    DBSession.flush()
    
    events_aggregate1 = CorrEvent( 
        idcause = event2.idevent,
        impact = 1,
        priority = 1,
        trouble_ticket = u'azerty1234',
        status = u'None',
        occurrence = 1,
        timestamp_active = datetime.now(),
    )
    events_aggregate1.events.append(event1)
    events_aggregate1.events.append(event2)
    DBSession.add(events_aggregate1)
    DBSession.flush()
        
    events_aggregate2 = CorrEvent( 
        idcause = event4.idevent,
        impact = 1,
        priority = 1,
        trouble_ticket = u'azerty1234',
        status = u'None',
        occurrence = 1,
        timestamp_active = datetime.now(),
    )
    events_aggregate2.events.append(event3)
    events_aggregate2.events.append(event4)
    DBSession.add(events_aggregate2)
    DBSession.flush()
    
    return [[event1.idevent, event2.idevent, event3.idevent, event4.idevent], 
            [events_aggregate1.idcorrevent, events_aggregate2.idcorrevent]]

class TestMergeAggregateFunction(unittest.TestCase):
    """Suite de tests de la fonction"""
    
    def setUp(self):
        """Initialisation de la BDD préalable à chacun des tests"""
        setup_db()
        
    def tearDown(self):
        """Nettoyage de la BDD à la fin de chaque test"""
        DBSession.flush()
        DBSession.expunge_all()
        teardown_db()
    
    def test_aggregates_merging(self):
        """Test de la fusion de 2 agrégats"""
        
        # Création de 4 couples host/service, 
        # 4 événéments et 2 agrégats dans la BDD.
        (events_id, aggregates_id) = create_topology_and_events()
        
        # On fusionne les 2 agrégats.
        res = merge_aggregates(aggregates_id[0], aggregates_id [1])
        
        aggregate1 = DBSession.query(CorrEvent
                    ).filter(CorrEvent.idcorrevent == aggregates_id[0]
                    ).first()
        
        # On vérifie que l'agrégat 1 a bien été supprimé        
        self.assertTrue(aggregate1 is None)
        
        aggregate2 = DBSession.query(CorrEvent
                    ).filter(CorrEvent.idcorrevent == aggregates_id[1]
                    ).first()
        
        # On vérifie que la cause de l'agrégat 2 est toujours l'événement 4
        self.assertTrue(aggregate2)
        self.assertEqual(aggregate2.idcause, events_id[3])
        
        events_id = []
        for event in aggregate2.events:
            events_id.append(event.idevent)
        events_id.sort()
         
        # On vérifie que l'agrégat 2 regroupe 
        # bien les événements 1, 2, 3 et 4
        self.assertEqual(events_id, 
            [events_id[0], events_id[1], events_id[2], events_id[3]])
        
        # On vérifie que le résultat retourné par la fonction 
        # merge_aggregates est bien la liste des ids des 
        # événements qui était auparavant rattachés à l'agrégat 1.
        self.assertEqual(res, [events_id[0], events_id[1]])
