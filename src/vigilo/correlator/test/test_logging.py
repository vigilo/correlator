# -*- coding: utf-8 -*-
# Copyright (C) 2006-2018 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""Suite de tests des logs du corrélateur"""

# pylint: disable-msg=C0111,W0212,R0904,W0201
# - C0111: Missing docstring
# - W0212: Access to a protected member of a client class
# - R0904: Too many public methods
# - W0201: Attribute defined outside __init__

import unittest
from datetime import datetime
import logging

from nose.twistedtools import reactor  # pylint: disable-msg=W0611
from nose.twistedtools import deferred

from twisted.internet import defer

from mock import Mock

from vigilo.models.session import DBSession
from vigilo.models.demo import functions
from vigilo.models.tables import Event, Change, SupItem, State

from vigilo.correlator.db_insertion import insert_event, insert_state
from vigilo.correlator.correvent import CorrEventBuilder
from vigilo.correlator.db_thread import DummyDatabaseWrapper

from vigilo.correlator.test import helpers

from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)



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


    @deferred(timeout=30)
    def setUp(self):
        # On prépare la base de données et le serveur MemcacheD.
        helpers.setup_db()
        self.context_factory = helpers.ContextStubFactory()

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
        self.msgid = 0
        return defer.succeed(None)

    @deferred(timeout=30)
    def tearDown(self):
        # On dissocie le handler du logger.
        self.logger.removeHandler(self.handler)
        helpers.teardown_db()
        return defer.succeed(None)


    @defer.inlineCallbacks
    def simulate_message_reception(self,
        new_state, host_name, service_name=None):
        """
        Génère un message de changement d'état concernant l'item passé en
        paramètre, réalise les mêmes traitements que ceux du rule_dispatcher
        et des règles, et déclenche l'exécution de la fonction make_correvent.
        """

        # On incrémente l'identifiant du message
        self.msgid += 1

        # On génère un timestamp à partir de la date courante
        timestamp = datetime.now()

        infos = {
            'type': "event",
            'id': self.msgid,
            'timestamp': timestamp,
            'service': service_name,
            'state': new_state,
            'message': new_state,
        }

        if host_name:
            infos['host'] = host_name
        else:
            infos['host'] = 'High-Level-Services'

        idsupitem = SupItem.get_supitem(host_name, service_name)

        # On ajoute les données nécessaires dans le contexte.
        ctx = self.context_factory(self.msgid)
        yield ctx.set('hostname', host_name)
        yield ctx.set('servicename', service_name)
        yield ctx.set('statename', new_state)
        yield ctx.set('idsupitem', idsupitem)

        # On insère les données nécessaires dans la BDD:
        info_dictionary = {
            "id": self.msgid,
            "host": host_name,
            "service": service_name,
            "state": new_state,
            "timestamp": timestamp,
            "message": new_state,
            "idsupitem": idsupitem,
        }

        # - D'abord l'évènement ;
        LOGGER.info("Inserting event")
        raw_id = insert_event(info_dictionary)
        yield ctx.set('raw_event_id', raw_id)
        # - Et ensuite l'état.
        LOGGER.info("Inserting state")
        # Si le timestamp est trop récent insert_state ne fera rien
        DBSession.query(State).get(idsupitem).timestamp = timestamp
        insert_state(info_dictionary)
        DBSession.flush()

        # On force le traitement du message, par la fonction make_correvent,
        # comme s'il avait été traité au préalable par le rule_dispatcher.
        corrbuilder = CorrEventBuilder(Mock(), DummyDatabaseWrapper(True))
        corrbuilder.context_factory = self.context_factory

        LOGGER.info('Creating a new correlated event')
        yield corrbuilder.make_correvent(info_dictionary)


    def add_data(self):
        """
        Ajoute un hôte et un service de bas niveau dans la BDD, ainsi
        que d'autres données nécessaires à l'exécution des tests.
        """
        helpers.populate_statename()

        # Ajout de la date de dernière
        # modification de la topologie dans la BDD.
        DBSession.add(Change(
            element = u"Topology",
            last_modified = datetime.now(),))
        DBSession.flush()

        self.host = functions.add_host(u'Host')
        self.lls = functions.add_lowlevelservice(self.host, u'LLS')


    @deferred(timeout=60)
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

        # Partie 1 : test le syslog sur la création d'un événement corrélé.

        # On recoit un message "WARNING" concernant lls1.
        LOGGER.debug("Received 'WARNING' message on lls1")
        ctx = self.context_factory(self.msgid)
        yield self.simulate_message_reception(u"WARNING", host_name, lls_name)

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
        ctx = self.context_factory(self.msgid + 1)
        yield ctx.set('update_id', event_id)
        yield self.simulate_message_reception(u"CRITICAL", host_name, lls_name)

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
