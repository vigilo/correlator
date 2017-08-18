# -*- coding: utf-8 -*-
# pylint: disable-msg=C0111,W0212,R0904
# Copyright (C) 2006-2016 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Teste la règle de gestion des services sur un hôte DOWN
"""

from __future__ import print_function
from datetime import datetime
import unittest

from nose.twistedtools import reactor  # pylint: disable-msg=W0611
from nose.twistedtools import deferred

from twisted.internet import defer
from mock import Mock

from vigilo.models import tables
from vigilo.models.demo import functions
from vigilo.models.session import DBSession

from vigilo.correlator.rules.svc_on_host_down import SvcHostDown
from vigilo.correlator.rules.svc_on_host_down import on_host_down
from vigilo.correlator.db_thread import DummyDatabaseWrapper
from vigilo.correlator.test import helpers


class TestRule(SvcHostDown):
    def _getTime(self):
        return 42


class TestSvcHostDownRule(unittest.TestCase):
    """
    Le setUp et le tearDown sont décorés par @deferred() pour que la création
    de la base soit réalisée dans le même threads que les accès dans les tests.
    """

    @deferred(timeout=60)
    def setUp(self):
        super(TestSvcHostDownRule, self).setUp()

        # Préparation de la base de données
        helpers.setup_db()
        self.host = self.lls = self.hls = None
        self.populate_db()

        # Préparation de la règle
        self.rule_dispatcher = helpers.RuleDispatcherStub()
        self.rule = TestRule()
        self.rule.set_database(DummyDatabaseWrapper(
                               disable_txn=True, async=False))
        self.rule._context_factory = helpers.ContextStubFactory()
        self.message_id = 42
        return defer.succeed(None)

    @deferred(timeout=60)
    def tearDown(self):
        super(TestSvcHostDownRule, self).tearDown()
        DBSession.flush()
        DBSession.expunge_all()
        helpers.teardown_db()
        return defer.succeed(None)


    def populate_db(self):
        helpers.populate_statename()
        self.host = functions.add_host(u'testhost')
        self.lls = functions.add_lowlevelservice(self.host, u'testservice')


    def setup_context(self, state_from, state_to):
        res = helpers.setup_context(
            self.rule._context_factory,
            self.message_id, {
                'previous_state':
                    tables.StateName.statename_to_value(unicode(state_from)),
                'statename': unicode(state_to),
                'timestamp': datetime.now(),
                'hostname': "testhost",
                'servicename': None,
        })
        ctx = self.rule._context_factory(self.message_id)
        ctx._connection._must_defer = False
        return res


    @deferred(timeout=60)
    @defer.inlineCallbacks
    def test_host_down(self):
        """Callback requis pour passer les services d'un hôte DOWN à UNKNOWN"""
        yield self.setup_context("UP", "DOWN")
        rule_dispatcher = Mock()
        yield self.rule.process(rule_dispatcher, self.message_id)
        print("Count:", rule_dispatcher.registerCallback.call_count)
        self.assertEqual(rule_dispatcher.registerCallback.call_count, 1)
        print(rule_dispatcher.registerCallback.call_args)
        self.assertEqual(
            rule_dispatcher.registerCallback.call_args[1]["fn"],
            on_host_down)


    @deferred(timeout=60)
    @defer.inlineCallbacks
    def test_on_host_down(self):
        """Fonction de passage à UNKNOWN des services d'un hôte DOWN"""
        yield self.setup_context("UP", "DOWN")
        # le timestamp par défaut est plus récent et insert_state refusera la
        # mise à jour
        self.lls.state.timestamp = datetime.fromtimestamp(1)
        yield on_host_down(
            None,
            None,
            DummyDatabaseWrapper(True),
            42,
            self.rule._context_factory(42)
        )
        print("state:", self.lls.state.name.statename)
        self.assertEqual(self.lls.state.name.statename, u"UNKNOWN")


    @deferred(timeout=60)
    @defer.inlineCallbacks
    def test_host_up(self):
        """Demander les états des services d'un hôte qui passe UP"""
        yield self.setup_context("DOWN", "UP")
        yield self.rule.process(self.rule_dispatcher, self.message_id)

        # On doit avoir envoyé 3 changements d'état identiques
        # + 1 un message de resynchronisation pour l'hôte.
        self.assertEqual(len(self.rule_dispatcher.buffer), 4)
        self.assertEqual(
            self.rule_dispatcher.buffer[-2],
            self.rule_dispatcher.buffer[-3],
        )
        self.assertEqual(
            self.rule_dispatcher.buffer[-3],
            self.rule_dispatcher.buffer[-4],
        )

        # On vérifie le contenu des changements d'état.
        expected = {"type": "nagios",
                    "timestamp": 42,
                    "cmdname": "PROCESS_SERVICE_CHECK_RESULT",
                    "value": "testhost;testservice;3;Host is down"
                    }
        recv = self.rule_dispatcher.buffer[-2]
        print("Received #1:", recv)
        self.assertEqual(recv, expected)

        # On vérifie la resynchronisation de l'hôte.
        expected = {"type": "nagios",
                    "timestamp": 42,
                    "cmdname": "SCHEDULE_HOST_SVC_CHECKS",
                    "value": "testhost;43"
                    }
        recv = self.rule_dispatcher.buffer[-1]
        print("Received #2:", recv)
        self.assertEqual(recv, expected)


    @deferred(timeout=60)
    @defer.inlineCallbacks
    def test_host_up_many_services(self):
        """Demander les états de tous les services d'un hôte qui passe UP"""
        yield self.setup_context("DOWN", "UP")
        servicenames = [ u'testservice-%d' % i for i in range(10) ]
        for servicename in servicenames:
            functions.add_lowlevelservice(self.host, servicename)
        rule_dispatcher = Mock()
        yield self.rule.process(rule_dispatcher, self.message_id)
        servicenames.insert(0, "testservice") # crée en setUp
        print("Count:", rule_dispatcher.sendItem.call_count)
        # 3 messages envoyés (changement d'état) par service
        # + 1 message de resynchro de l'hôte
        self.assertEqual(
            rule_dispatcher.sendItem.call_count,
            len(servicenames) * 3 + 1
        )

        # On vérifie qu'il y a bien eu 3 messages
        # de resynchronisation par service.
        for i, servicename in enumerate(servicenames):
            for j in xrange(3):
                call = rule_dispatcher.method_calls[i * 3 + j]
                print(servicename, call)
                self.assertEqual(call[0], "sendItem")
                self.assertEqual(call[1][0]["cmdname"],
                    "PROCESS_SERVICE_CHECK_RESULT")
                self.assertEqual(call[1][0]["value"].count(
                    "%s;%s;" % (self.host.name, servicename)), 1)
        # + 1 message de resynchronisation
        # pour (l'ensemble des services de) l'hôte.
        call = rule_dispatcher.method_calls[len(servicenames) * 3]
        self.assertEqual(call[1][0]["value"].count(self.host.name + ';'), 1)
        self.assertEqual(call[1][0]["cmdname"], "SCHEDULE_HOST_SVC_CHECKS")

