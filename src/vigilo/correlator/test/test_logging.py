# -*- coding: utf-8 -*-
# pylint: disable-msg=C0111,W0212,R0904
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""Suite de tests des logs du corrélateur"""

import unittest
from nose.twistedtools import reactor, deferred
from twisted.internet import defer

from datetime import datetime
from lxml import etree
import logging

from helpers import settings, populate_statename
from helpers import setup_mc, teardown_mc, setup_db, teardown_db
from vigilo.models.session import DBSession
from vigilo.models.tables import LowLevelService, Host, StateName, \
                            Event, Change

from vigilo.pubsub.xml import NS_EVENT
from vigilo.correlator.context import Context
from vigilo.correlator.db_insertion import insert_event, insert_state
from vigilo.correlator.correvent import make_correvent
from vigilo.correlator.db_thread import DummyDatabaseWrapper

from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)

class RuleDispatcherStub():
    """Classe simulant le fonctionnement du RuleDispatcher."""

    def __init__(self, *args):
        """Initialisation."""
        self.buffer = []

    def sendItem(self, item):
        """Simule l'écriture d'un message sur la file"""
        self.buffer.append(item)

    def clear(self):
        """Vide la file de messages"""
        self.buffer = []


class LogHandlerStub(object):
    """Classe interceptant les logs du corrélateur pendant les tests."""

     # Attribut statique de classe
    instance = None

    def __init__(self):
        """Initialisation."""
        self.buffer = []

    def write(self, message):
        """
        Écrit les messages dans le buffer.

        @param message: Le message à enregistrer.
        @type message: C{str}
        """
        LOGGER.debug("Ajout du message '%s' dans le syslog" % (message, ))
        self.buffer.append(message)

    def flush(self):
        """
        Simule la méthode flush des streams.
        """
        pass

    def clear(self):
        """
        Vide le buffer de messages.
        """
        self.buffer = []

class TestLogging(unittest.TestCase):
    """
    Test de l'écriture des logs dans le corrélateur.

    Valide la satisfaction de l'exigence VIGILO_EXIG_VIGILO_COR_0040.

    Le setUp et le tearDown sont décorés par @deferred() pour que la création
    de la base soit réalisée dans le même threads que les accès dans les tests.
    """

    @defer.inlineCallbacks
    def simulate_message_reception(self,
        new_state, host_name, service_name=None):
        """
        Génère un message de changement d'état concernant l'item passé en
        paramètre, réalise les mêmes traitements que ceux du rule_dispatcher
        et des règles, et déclenche l'exécution de la fonction make_correvent.
        """

        # On incrémente l'identifiant du message
        self.XMPP_id += 1

        # On génère un timestamp à partir de la date courante
        timestamp = datetime.now()

        infos = {
            'xmlns': NS_EVENT,
            'ts': timestamp,
            'service': service_name,
            'state': new_state,
            'xmpp_id': self.XMPP_id,
        }

        if host_name:
            infos['host'] = host_name
        else:
            infos['host'] = settings['correlator']['nagios_hls_host']

        payload = """
<event xmlns="%(xmlns)s">
    <timestamp>%(ts)s</timestamp>
    <host>%(host)s</host>
    <service>%(service)s</service>
    <state>%(state)s</state>
    <message>%(state)s</message>
</event>
""" % infos
        item = etree.fromstring(payload)

        # On ajoute les données nécessaires dans le contexte.
        ctx = Context(self.XMPP_id, database=DummyDatabaseWrapper(True))
        yield ctx.set('hostname', host_name)
        yield ctx.set('servicename', service_name)
        yield ctx.set('statename', new_state)

        # On insère les données nécessaires dans la BDD:
        info_dictionary = {
            "host": host_name,
            "service": service_name,
            "state": new_state,
            "timestamp": timestamp,
            "message": new_state,
        }

        # - D'abord l'évènement ;
        yield ctx.set('raw_event_id', insert_event(info_dictionary))
        # - Et ensuite l'état.
        insert_state(info_dictionary)
        DBSession.flush()

        # On force le traitement du message, par la fonction make_correvent,
        # comme s'il avait été traité au préalable par le rule_dispatcher.
        rd = RuleDispatcherStub()

        LOGGER.error('Creating new correlated event')
        yield make_correvent(rd, DummyDatabaseWrapper(True), item, self.XMPP_id)

    def add_data(self):
        """
        Ajoute un hôte et un service de bas niveau dans la BDD, ainsi
        que d'autres données nécessaires à l'exécution des tests.
        """

        # Ajout d'états dans la BDD.
        populate_statename()

        # Ajout de la date de dernière
        # modification de la topologie dans la BDD.
        DBSession.add(Change(
            element = u"Topology",
            last_modified = datetime.now(),))
        DBSession.flush()

        # Ajout d'un hôte dans la BDD.
        self.host = Host(
            name = u'Host',
            checkhostcmd = u'check11',
            snmpcommunity = u'com11',
            hosttpl = u'tpl11',
            address = u'192.168.0.11',
            snmpport = 11,
            weight = 42,
        )
        DBSession.add(self.host)
        DBSession.flush()

        # Ajout d'un service de bas niveau dans la BDD.
        self.lls = LowLevelService(
            servicename = u'LLS',
            host = self.host,
            command = u'halt',
            weight = 42,
        )
        DBSession.flush()

    @deferred(timeout=30)
    def setUp(self):
        """Initialisation des tests"""

        # On prépare la base de données et le serveur MemcacheD.
        setup_mc()
        setup_db()

        # On récupère le logger 'vigilo.correlator.syslog'
        # défini dans les settings.
        self.logger = get_logger('vigilo.correlator.syslog')

        # On crée une instance de la classe test_log_handler()
        # pour intercepter les logs du corrélateur, et on
        # construit un StreamHandler à partir de cette instance.
        self.stream = LogHandlerStub()
        self.handler = logging.StreamHandler(self.stream)

        # On associe ce handler au logger.
        self.logger.addHandler(self.handler)

        # On crée un formatter (qui comme son nom l'indique permet de
        # spécifier le format des messages) qu'on associe lui-même au handler.
        formatter = logging.Formatter("%(message)s")
        self.handler.setFormatter(formatter)

        # Initialisation de l'identifiant des messages XML.
        self.XMPP_id = 0
        return defer.succeed(None)

    @deferred(timeout=30)
    def tearDown(self):
        """Nettoie MemcacheD et la BDD à la fin de chaque test."""
        # On dissocie le handler du logger.
        self.logger.removeHandler(self.handler)

        DBSession.flush()
        # Évite que d'anciennes instances viennent perturber le test suivant.
        DBSession.expunge_all()
        teardown_db()
        teardown_mc()
        return defer.succeed(None)

    @deferred(timeout=30)
    @defer.inlineCallbacks
    def test_syslog_and_correvent(self):
        """
        Syslog : création et mise à jour d'un événement corrélé.

        Vérifie que les logs générés lors de la création d'un nouvel
        évènement par le corrélateur sont conformes à ceux attendus.
        Puis, fait de même avec la mise à jour d'un événement corrélé.
        """

        # Insertion de données dans la base.
        self.add_data()

        DBSession.add(self.host)
        DBSession.add(self.lls)

        host_name = self.host.name

        lls_name = self.lls.servicename
        lls_id = self.lls.idservice

        # Partie 1 : test le syslog sur la création d'un événement corrélé.

        # On recoit un message "WARNING" concernant lls1.
        LOGGER.debug("Received 'WARNING' message on lls1")
        ctx = Context(self.XMPP_id, database=DummyDatabaseWrapper(True))
        self.simulate_message_reception(u"WARNING", host_name, lls_name)

        event = DBSession.query(Event.idevent).one()
        event_id = event.idevent

        self.assertEqual(
            self.stream.buffer, [u'%(idevent)d|NEW|%(hostname)s|'
            '%(servicename)s|%(statename)s|%(priority)s|%(statename)s\n' % {
                'idevent': event_id,
                'hostname': host_name,
                'servicename': lls_name,
                'statename': u'WARNING',
                'priority': 4,
                }])

        self.stream.clear()

        # Partie 2 : test le syslog sur la mise à jour d'un événement corrélé.

        # On recoit un message "CRITICAL" concernant lls1.
        LOGGER.debug("Received 'CRITICAL' message on lls1")
        ctx = Context(self.XMPP_id + 1, database=DummyDatabaseWrapper(True))
        yield ctx.set('update_id', event_id)
        self.simulate_message_reception(u"CRITICAL", host_name, lls_name)

        event = DBSession.query(Event.idevent).one()
        event_id = event.idevent

        self.assertEqual(
            self.stream.buffer, [u'%(idevent)d|CHANGE|%(hostname)s|'
            '%(servicename)s|%(statename)s|%(priority)s|%(statename)s\n' % {
                'idevent': event_id,
                'hostname': host_name,
                'servicename': lls_name,
                'statename': u'CRITICAL',
                'priority': 4,
                }])

        self.stream.clear()
