# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""
Test du module publish_messages.
"""

import unittest

from vigilo.correlator.publish_messages import publish_aggregate, \
                                            delete_published_aggregates, \
                                            publish_state
from utils import setup_db, teardown_db
  
from vigilo.models.configure import DBSession
from vigilo.models import Host, HighLevelService, LowLevelService
from vigilo.models import State, StateName

from datetime import datetime
from time import mktime

from vigilo.common.conf import settings
settings.load_module(__name__)


class Queue():
    """Classe simulant une queue de messages"""
    def __init__(self):
        self.buffer = []
    def put_nowait(self, value):
        """Simule l'écriture d'un message sur la file"""
        self.buffer.append(value)
    def clear(self):
        """Vide la file de messages"""
        self.buffer = []

class TestAggregatesHandlerFunctions(unittest.TestCase):
    """Suite de tests du module publish_messages"""
    
    def setUp(self):
        """Initialisation d'une queue de messages"""
        self.queue = Queue()
    
    def test_publish_aggregate(self):
        """Publication XMPP d'alertes à ajouter à des évènements corrélés"""
        publish_aggregate(self.queue, [1, 2], [1, 2, 3, 4]) 
        
        message = [u"<aggr xmlns='http://www.projet-vigilo.org/xmlns/aggr1'>"
            "<aggregates><aggregate>1</aggregate><aggregate>2</aggregate>"
            "</aggregates><alerts><alert>1</alert><alert>2</alert>"
            "<alert>3</alert><alert>4</alert></alerts></aggr>"]
        
        self.assertEqual(self.queue.buffer, message)
        
    def test_delete_published_aggregates(self):
        """Publication XMPP d'une liste d'évènements corrélés à supprimer"""
        delete_published_aggregates(self.queue, [1, 2])
        
        message = [u"<delaggr xmlns='http://www.projet-vigilo.org/xmlns/"
            "delaggr1'><aggregates><aggregate>1</aggregate>"
            "<aggregate>2</aggregate></aggregates></delaggr>"]
        
        self.assertEqual(self.queue.buffer, message)
    
    def test_publish_state(self):
        """Publication XMPP de l'état d'un item"""
        
        # Initialisation de la BDD
        setup_db()
        
        # Ajout d'un hôte dans la BDD
        host1 = Host(
            name = u'host1.example.com',
            checkhostcmd = u'check11',
            snmpcommunity = u'com11',
            hosttpl = u'tpl11',
            mainip = u'192.168.0.11',
            snmpport = 11,
            weight = 100,
        )
        DBSession.add(host1)
        DBSession.flush()
        
        # Ajout d'un service de haut niveau dans la BDD
        hls1 = HighLevelService(
            servicename = u'Connexion',
            message = u'Ouch',
            warning_threshold = 300,
            critical_threshold = 150,
            op_dep = u'&',
            priority = 1,
        )
        DBSession.add(hls1)
        DBSession.flush()
        
        # Ajout d'un service de bas niveau dans la BDD
        lls1 = LowLevelService(
            servicename = u'Processes',
            host = host1,
            command = u'halt',
            op_dep = u'&',
            weight = 100,
        )
        DBSession.add(lls1)
        DBSession.flush()
        
        # Ajout des noms d'états dans la BDD
        DBSession.add(StateName(
            statename = u'OK',
            order = 0))
        DBSession.add(StateName(
             statename = u'UNKNOWN',
            order = 1))
        DBSession.add(StateName(
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
        
        # Création d'un timestamp à partir de l'heure actuelle
        timestamp = datetime.now()
        int_timestamp = int(mktime(timestamp.timetuple()))
        
        # Ajout de l'état du host1 dans la BDD
        state1 = State(
            idsupitem = host1.idhost,
            timestamp = timestamp,
            state = StateName.statename_to_value(u"UNREACHABLE"),
            message = "UNREACHABLE: Host1")
        DBSession.add(state1)
        DBSession.flush()
        
        info_dictionary = {"host": "host1.example.com",
                           "service": None,
                           "timestamp": state1.timestamp,
                           "state": StateName.value_to_statename(state1.state),
                           "message": state1.message}
        
        # On publie l'état du host1 sur le bus
        publish_state(self.queue, info_dictionary)
        
        message = [u"<state xmlns='http://www.projet-vigilo.org/xmlns/state1'>"
            "<timestamp>" + str(int_timestamp) + "</timestamp>"
            "<host>host1.example.com</host>"
            "<state>UNREACHABLE</state>"
            "<message>UNREACHABLE: Host1</message></state>"]
        
        # On vérifie que le message publié sur le bus concernant
        # l'état du host1 est bien celui attendu.
        self.assertEqual(self.queue.buffer, message)
        
        # On vide le bus entre 2 tests
        self.queue.clear()
        
        # Ajout de l'état du hls1 dans la BDD
        state2 = State(
            idsupitem = hls1.idservice,
            timestamp = timestamp,
            state = StateName.statename_to_value(u"UNKNOWN"),
            message = "UNKNOWN: Connection is in an unknown state")
        DBSession.add(state2)
        DBSession.flush()
        
        info_dictionary = {"host": settings['correlator']['nagios_hls_host'],
                           "service": "Connexion",
                           "timestamp": state2.timestamp,
                           "state": StateName.value_to_statename(state2.state),
                           "message": state2.message}
        
        # On publie l'état du hls1 sur le bus
        publish_state(self.queue, info_dictionary)
        
        message = [u"<state xmlns='http://www.projet-vigilo.org/xmlns/state1'>"
            "<timestamp>" + str(int_timestamp) + "</timestamp>"
            "<host>" + settings['correlator']['nagios_hls_host'] + "</host>"
            "<service>Connexion</service>"
            "<state>UNKNOWN</state>"
            "<message>UNKNOWN: Connection is in an unknown state</message>"
            "</state>"]
        
        # On vérifie que le message publié sur le bus concernant
        # l'état du hls1 est bien celui attendu.
        self.assertEqual(self.queue.buffer, message)
        
        # On vide le bus entre 2 tests
        self.queue.clear()
        
        # Ajout de l'état du lls1 dans la BDD
        state3 = State(
            idsupitem = lls1.idservice,
            timestamp = timestamp,
            state = StateName.statename_to_value(u"UNKNOWN"),
            message = "UNKNOWN: Processes are in an unknown state")
        DBSession.add(state3)
        DBSession.flush()
        
        info_dictionary = {"host": "host1.example.com",
                           "service": "Processes",
                           "timestamp": state3.timestamp,
                           "state": StateName.value_to_statename(state3.state),
                           "message": state3.message}
        
        # On publie l'état du lls1 sur le bus
        publish_state(self.queue, info_dictionary)
        
        message = [u"<state xmlns='http://www.projet-vigilo.org/xmlns/state1'>"
            "<timestamp>" + str(int_timestamp) + "</timestamp>"
            "<host>host1.example.com</host>"
            "<service>Processes</service>"
            "<state>UNKNOWN</state>"
            "<message>UNKNOWN: Processes are in an unknown state</message>"
            "</state>"]
        
        # On vérifie que le message publié sur le bus concernant
        # l'état du lls1 est bien celui attendu.
        self.assertEqual(self.queue.buffer, message)

        DBSession.flush()
        DBSession.expunge_all()
        teardown_db()

