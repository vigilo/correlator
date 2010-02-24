# -*- coding: utf-8 -*-
"""Suite de tests des fonctions réalisant des insertions dans la BDD."""
from datetime import datetime
import unittest
import time

from vigilo.correlator.actors.rule_dispatcher import extract_information
from vigilo.correlator.db_insertion import insert_event, insert_state, \
                                        add_to_aggregate
from vigilo.correlator.libs import etree
from vigilo.correlator.xml import NS_EVENTS
from utils import setup_db, teardown_db

from vigilo.models import State, StateName, Event, \
                            LowLevelService, HighLevelService, Host, \
                            CorrEvent
from vigilo.models.configure import DBSession
from vigilo.common.conf import settings
settings.load_module(__name__)

class TestDbInsertion(unittest.TestCase):
    """Teste l'insertion de données dans la BDD."""

    def setUp(self):
        """Set up the fixture used to test the model."""
        print "setting up the database"
        setup_db()
        DBSession.add(StateName(statename=u'OK', order=0))
        DBSession.add(StateName(statename=u'UP', order=0))
        DBSession.add(StateName(statename=u'WARNING', order=2))
        DBSession.add(StateName(statename=u'DOWN', order=3))
        DBSession.flush()

    def tearDown(self):
        """Tear down the fixture used to test the model."""
        print "tearing down the database"
        DBSession.flush()
        # Évite que d'anciennes instances viennent perturber le test suivant.
        DBSession.expunge_all()
        teardown_db()

    def make_dependancies(self):
        """Création de quelques dépendances dans la BDD."""
        host = Host(
            name=u'server.example.com',
            checkhostcmd=u'halt',
            hosttpl=u'',
            mainip=u'127.0.0.1',
            snmpcommunity=u'public',
            snmpport=42,
            weight=42,
        )
        DBSession.add(host)
        DBSession.add(LowLevelService(
            servicename=u'Load',
            host=host,
            op_dep=u'+',
            weight=42,
        ))

        DBSession.add(HighLevelService(
            servicename=u'Load',
            op_dep=u'+',
            message=u'Ouch',
            warning_threshold=100,
            critical_threshold=80,
            priority=1,
        ))
        DBSession.flush()


    def test_insert_lls_event(self):
        """Insertion d'un évènement brut concernant un SBN"""

        self.make_dependancies()

        # Création d'un message d'événement portant sur un SBN.
        xml = """
<event xmlns="%(xmlns)s">
    <timestamp>1239104006</timestamp>
    <host>server.example.com</host>
    <service>Load</service>
    <state>WARNING</state>
    <message>WARNING: Load average is above 4 (4.5)</message>
</event>""" % {'xmlns': NS_EVENTS}

        # Extraction des informations du messages
        info_dictionary = extract_information(etree.fromstring(xml))
        # Insertion de l'événement dans la BDD
        idevent = insert_event(info_dictionary)
        
        assert idevent is not None
        event = DBSession.query(Event).one()

        # Vérification des informations de l'événement dans la BDD.
        self.assertEquals(LowLevelService, type(event.supitem))
        self.assertEquals(1239104006, time.mktime(event.timestamp.timetuple()))
        self.assertEquals(u'server.example.com', event.supitem.host.name)
        self.assertEquals(u'Load', event.supitem.servicename)
        self.assertEquals(u'WARNING',
            StateName.value_to_statename(event.current_state))
        self.assertEquals(u'WARNING',
            StateName.value_to_statename(event.initial_state))
        self.assertEquals(u'WARNING',
            StateName.value_to_statename(event.peak_state))
        self.assertEquals(u'WARNING: Load average is above 4 (4.5)',
                            event.message)
        
        # Insertion de l'état dans la BDD
        insert_state(info_dictionary)
        
        state = DBSession.query(State).one()

        # Vérification des informations de l'état dans la BDD.
        self.assertEquals(LowLevelService, type(state.supitem))
        self.assertEquals(1239104006, time.mktime(state.timestamp.timetuple()))
        self.assertEquals('server.example.com', state.supitem.host.name)
        self.assertEquals('Load', state.supitem.servicename)
        self.assertEquals('WARNING',
            StateName.value_to_statename(state.state))
        self.assertEquals('WARNING: Load average is above 4 (4.5)',
                            state.message)

    def test_insert_hls_event(self):
        """Insertion d'un évènement brut concernant un SHN"""

        self.make_dependancies()

        # Création d'un message d'événement portant sur un SHN.
        xml = """
<event xmlns="%(xmlns)s">
    <timestamp>1239104006</timestamp>
    <host>%(hls_host)s</host>
    <service>Load</service>
    <state>WARNING</state>
    <message>WARNING: Load average is above 4 (4.5)</message>
</event>""" % {'xmlns': NS_EVENTS, 'hls_host': settings['correlator']['nagios_hls_host']}

        # Extraction des informations du messages
        info_dictionary = extract_information(etree.fromstring(xml))

        # Insertion de l'événement dans la BDD
        idevent = insert_event(info_dictionary)

        # Aucun événement ne doit être créé 
        # pour les services de haut niveau.
        assert idevent is None

    def test_insert_host_event(self):
        """Insertion d'un évènement brut concernant un hôte"""

        self.make_dependancies()

        # Création d'un message d'événement portant sur un hôte.
        xml = """
<event xmlns="%(xmlns)s">
    <timestamp>1239104006</timestamp>
    <host>server.example.com</host>
    <state>DOWN</state>
    <message>DOWN: No ping response</message>
</event>""" % {'xmlns': NS_EVENTS}

        # Extraction des informations du messages
        info_dictionary = extract_information(etree.fromstring(xml))
        
        # Insertion de l'événement dans la BDD
        idevent = insert_event(info_dictionary)

        assert idevent is not None
        event = DBSession.query(Event).one()

        # Vérification des informations de l'événement dans la BDD.
        self.assertEquals(Host, type(event.supitem))
        self.assertEquals(1239104006, time.mktime(event.timestamp.timetuple()))
        self.assertEquals(u'server.example.com', event.supitem.name)
        self.assertEquals(u'DOWN',
            StateName.value_to_statename(event.current_state))
        self.assertEquals(u'DOWN',
            StateName.value_to_statename(event.initial_state))
        self.assertEquals(u'DOWN',
            StateName.value_to_statename(event.peak_state))
        self.assertEquals(u'DOWN: No ping response',
                            event.message)
        
        # Insertion de l'état dans la BDD
        insert_state(info_dictionary)
        
        state = DBSession.query(State).one()
        
        # Vérification des informations de l'état dans la BDD.
        self.assertEquals(Host, type(state.supitem))
        self.assertEquals(1239104006, time.mktime(state.timestamp.timetuple()))
        self.assertEquals('server.example.com', state.supitem.name)
        self.assertEquals('DOWN',
            StateName.value_to_statename(state.state))
        self.assertEquals('DOWN: No ping response', state.message)


#    def test_history_on_modification(self):
#        """
#        Teste si une entrée est correctement ajoutée à
#        l'historique lorsqu'un évènement est modifié.
#        """
#        xml = """
#<correvent xmlns="http://www.projet-vigilo.org/messages">
#    <timestamp>1239104006</timestamp>
#    <host>server.example.com</host>
#    <ip>192.168.1.2</ip>
#    <service>Load</service>
#    <state>WARNING</state>
#    <message>WARNING: Load average is above 4 (5.2)</message>
#    <impact count="130">
#        <host>server2.example.com</host>
#        <host>server3.example.com</host>
#    </impact>
#    <highlevel>
#        <service>WAN</service>
#        <service>LAN</service>
#    </highlevel>
#    <priority>5</priority>
#</correvent>"""
#        nodetodbfw.handleCorrEvent(parseXml(xml), u"bar")

#        # Modification de l'état (state).
#        xml = """
#<correvent update="bar" xmlns="http://www.projet-vigilo.org/messages">
#    <timestamp>1239104008</timestamp>
#    <host>server.example.com</host>
#    <ip>192.168.1.2</ip>
#    <service>Load</service>
#    <state>OK</state>
#    <message>RECOVERY: Load average is below 4 (3.2)</message>
#    <impact count="130">
#        <host>server2.example.com</host>
#        <host>server3.example.com</host>
#    </impact>
#    <highlevel>
#        <service>WAN</service>
#        <service>LAN</service>
#    </highlevel>
#</correvent>"""
#        nodetodbfw.handleCorrEvent(parseXml(xml), u"bar")

#        history = DBSession.query(EventHistory).all()
#        self.assertEquals(1, len(history),
#            "Expected 1 entry in history, got %d" % len(history))

#        # Modification de l'état et de la gravité (state & priority).
#        # On doit prendre en compte l'entrée déjà ajoutée auparavant.
#        xml = """
#<correvent update="bar" xmlns="http://www.projet-vigilo.org/messages">
#    <timestamp>1239104010</timestamp>
#    <host>server.example.com</host>
#    <ip>192.168.1.2</ip>
#    <service>Load</service>
#    <state>CRITICAL</state>
#    <message>CRITICAL: Load average is above 5 (5.2)</message>
#    <impact count="130">
#        <host>server2.example.com</host>
#        <host>server3.example.com</host>
#    </impact>
#    <highlevel>
#        <service>WAN</service>
#        <service>LAN</service>
#        <service>SMTP</service>
#    </highlevel>
#    <priority>7</priority>
#</correvent>"""
#        nodetodbfw.handle_correlated_event(parseXml(xml), u"bar")

#        history = DBSession.query(EventHistory).all()
#        self.assertEquals(3, len(history),
#            "Expected 3 entries in history, got %d" % len(history))

    def test_add_to_agregate(self):
        """Ajout d'un événement brut à un évènement corrélé déjà existant"""
        # On crée 2 couples host/service.
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
        
        # On ajoute 1 couple événement/agrégat à la BDD.
        event2 = Event(
            idsupitem = service2.idservice,
            current_state = 2,
            message = 'WARNING: CPU is overloaded',
            timestamp = datetime.now(),
        )
        DBSession.add(event2)
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
        events_aggregate1.events.append(event2)
        DBSession.add(events_aggregate1)
        DBSession.flush()
            
        # On ajoute un nouvel événement à la BDD.
        event1 = Event(
            idsupitem = service1.idservice,
            current_state = 2,
            message = 'WARNING: Processes are not responding',
            timestamp = datetime.now(),
        )
        DBSession.add(event1)
        DBSession.flush()
        
        # On ajoute ce nouvel événement à l'agrégat existant.
        add_to_aggregate(event1.idevent, events_aggregate1)
        
        # On vérifie que l'événement a bien été ajouté à l'agrégat.
        self.assertTrue(event1 in events_aggregate1.events )


if __name__ == "__main__": 
    unittest.main()

