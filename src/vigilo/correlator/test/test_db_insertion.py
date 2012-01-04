# -*- coding: utf-8 -*-
# pylint: disable-msg=C0111,W0212,R0904
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""Suite de tests des fonctions réalisant des insertions dans la BDD."""
from datetime import datetime
import unittest
import time
from lxml import etree

from vigilo.correlator.actors.rule_dispatcher import extract_information
from vigilo.correlator.db_insertion import insert_event, insert_state, \
                                    OldStateReceived, NoProblemException
from vigilo.correlator.db_thread import DummyDatabaseWrapper
from vigilo.pubsub.xml import NS_EVENT
import helpers

from vigilo.models.tables import State, StateName, Event, SupItem, \
                            LowLevelService, HighLevelService, Host, \
                            CorrEvent
from vigilo.models.session import DBSession

class TestDbInsertion(unittest.TestCase):
    """Teste l'insertion de données dans la BDD."""

    def setUp(self):
        super(TestDbInsertion, self).setUp()
        helpers.setup_db()
        helpers.populate_statename()

    def tearDown(self):
        helpers.teardown_db()
        super(TestDbInsertion, self).tearDown()

    def make_dependencies(self):
        """Création de quelques dépendances dans la BDD."""
        host = Host(
            name=u'server.example.com',
            hosttpl=u'',
            address=u'127.0.0.1',
            snmpcommunity=u'public',
            snmpport=42,
            weight=42,
        )
        DBSession.add(host)
        DBSession.add(LowLevelService(
            servicename=u'Load',
            host=host,
            weight=42,
        ))

        DBSession.add(HighLevelService(
            servicename=u'Load',
            message=u'Ouch',
            warning_threshold=100,
            critical_threshold=80,
        ))
        DBSession.flush()


    def test_insert_lls_event(self):
        """Insertion d'un évènement brut concernant un SBN"""

        self.make_dependencies()

        # Création d'un message d'événement portant sur un SBN.
        xml = """
<event xmlns="%(xmlns)s">
    <timestamp>1239104006</timestamp>
    <host>server.example.com</host>
    <service>Load</service>
    <state>WARNING</state>
    <message>WARNING: Load average is above 4 (4.5)</message>
</event>""" % {'xmlns': NS_EVENT}

        # Extraction des informations du messages
        info_dictionary = extract_information(etree.fromstring(xml))
        info_dictionary['idsupitem'] = SupItem.get_supitem(
            info_dictionary['host'],
            info_dictionary['service']
        )

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
        state = DBSession.query(State).get(info_dictionary['idsupitem'])
        # le timestamp par défaut est plus récent et insert_state refusera la
        # mise à jour
        state.timestamp = info_dictionary['timestamp']
        insert_state(info_dictionary)

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

        self.make_dependencies()

        # Création d'un message d'événement portant sur un SHN.
        xml = """
<event xmlns="%(xmlns)s">
    <timestamp>1239104006</timestamp>
    <host>%(hls_host)s</host>
    <service>Load</service>
    <state>WARNING</state>
    <message>WARNING: Load average is above 4 (4.5)</message>
</event>""" % {
            'xmlns': NS_EVENT,
            'hls_host': helpers.settings['correlator']['nagios_hls_host'],
        }

        # Extraction des informations du messages
        info_dictionary = extract_information(etree.fromstring(xml))
        info_dictionary['idsupitem'] = SupItem.get_supitem(
            info_dictionary['host'],
            info_dictionary['service']
        )

        # Insertion de l'événement dans la BDD
        idevent = insert_event(info_dictionary)

        # Aucun événement ne doit être créé
        # pour les services de haut niveau.
        assert idevent is None

    def test_insert_host_event(self):
        """Insertion d'un évènement brut concernant un hôte"""

        self.make_dependencies()

        # Création d'un message d'événement portant sur un hôte.
        xml = """
<event xmlns="%(xmlns)s">
    <timestamp>1239104006</timestamp>
    <host>server.example.com</host>
    <state>DOWN</state>
    <message>DOWN: No ping response</message>
</event>""" % {'xmlns': NS_EVENT}

        # Extraction des informations du messages
        info_dictionary = extract_information(etree.fromstring(xml))
        info_dictionary['idsupitem'] = SupItem.get_supitem(
            info_dictionary['host'],
            info_dictionary['service']
        )

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
        state = DBSession.query(State).get(info_dictionary['idsupitem'])
        # le timestamp par défaut est plus récent et insert_state refusera la
        # mise à jour
        state.timestamp = info_dictionary['timestamp']
        insert_state(info_dictionary)

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

    def test_insert_old_state(self):
        """Abandon de l'insertion d'un état ancien"""
        self.make_dependencies()
        ts_old = "1239104006"
        ts_recent = "1239104042"
        ts_recent_dt = datetime.fromtimestamp(int(ts_recent))
        idsupitem = SupItem.get_supitem("server.example.com", "Load")
        # Insertion de l'état récent
        state = DBSession.query(State).get(idsupitem)
        state.timestamp = ts_recent_dt
        # Création d'un message d'événement portant sur un SBN.
        xml = """
<event xmlns="%(xmlns)s">
    <timestamp>%(ts_old)s</timestamp>
    <host>server.example.com</host>
    <service>Load</service>
    <state>WARNING</state>
    <message>WARNING: Load average is above 4 (4.5)</message>
</event>""" % {'xmlns': NS_EVENT, "ts_old": ts_old}

        # Extraction des informations du messages
        info_dictionary = extract_information(etree.fromstring(xml))
        info_dictionary['idsupitem'] = SupItem.get_supitem(
            info_dictionary['host'],
            info_dictionary['service']
        )
        # Insertion de l'ancien événement dans la BDD
        result = insert_state(info_dictionary)
        self.assertTrue(isinstance(result, OldStateReceived))
        supitem = DBSession.query(SupItem).get(idsupitem)
        self.assertEqual(supitem.state.timestamp, ts_recent_dt)

    def test_no_problem_exception(self):
        """Exception à réception d'une alerte n'indiquant aucun problème."""
        self.make_dependencies()
        xml = """
<event xmlns="%(xmlns)s">
    <timestamp>%(ts)s</timestamp>
    <host>server.example.com</host>
    <service>Load</service>
    <state>OK</state>
    <message>No problem here</message>
</event>""" % {'xmlns': NS_EVENT, "ts": int(time.time())}

        # Extraction des informations du messages
        info_dictionary = extract_information(etree.fromstring(xml))
        info_dictionary['idsupitem'] = SupItem.get_supitem(
            info_dictionary['host'],
            info_dictionary['service']
        )
        self.assertRaises(NoProblemException, insert_event, info_dictionary)
