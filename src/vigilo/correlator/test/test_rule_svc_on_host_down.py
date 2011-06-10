# -*- coding: utf-8 -*-
# pylint: disable-msg=C0111,W0212,R0904
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Teste la règle de gestion des services sur un hôte DOWN
"""

from datetime import datetime
import time
#import unittest

#from nose.twistedtools import reactor, deferred
from twisted.trial import unittest
from twisted.internet import defer
from mock import Mock

from lxml import etree

from vigilo.models import tables
from vigilo.models.session import DBSession
from vigilo.pubsub.xml import NS_COMMAND

from vigilo.correlator.context import Context
from vigilo.correlator.amp.commands import SendToBus

from vigilo.correlator.rules.svc_on_host_down import SvcHostDown, NAGIOS_MESSAGE

from helpers import setup_db, teardown_db, setup_context, populate_statename, \
    ContextStubFactory, RuleRunnerStub


class TestSvcHostDownRule(unittest.TestCase):

    def setUp(self):
        super(TestSvcHostDownRule, self).setUp()

        # Préparation de la base de données
        setup_db()
        self.host = self.lls = self.hls = None
        self.populate_db()

        # Préparation de la règle
        self.rule_runner = RuleRunnerStub()
        self.rule = SvcHostDown()
        self.rule._context_factory = ContextStubFactory()
        self.message_id = 42

    def tearDown(self):
        super(TestSvcHostDownRule, self).tearDown()
        DBSession.flush()
        DBSession.expunge_all()
        teardown_db()

    def populate_db(self):
        populate_statename()
        self.host = tables.Host(
            name = u'testhost',
            checkhostcmd = u'',
            hosttpl = u'',
            address = u'127.0.0.1',
            snmpcommunity = u'public',
            snmpport = 42,
            weight = 42,
        )
        DBSession.add(self.host)
        self.lls = tables.LowLevelService(
            host = self.host,
            servicename = u'testservice',
            weight = 42,
        )
        DBSession.add(self.lls)
        DBSession.flush()

    @defer.inlineCallbacks
    def test_host_down(self):
        """Marquer UNKNOWN les services d'un hôte DOWN"""
        yield setup_context(
            self.rule._context_factory,
            self.message_id, {
                'statename': u"DOWN",
                'previous_state': tables.StateName.statename_to_value(u"UP"),
                'timestamp': 42,
                'hostname': "testhost",
                'servicename': None
        })
        yield self.rule.process(None, self.message_id, None)
        print "state:", self.lls.state.name.statename
        # Il ne faut pas utiliser self.assertEqual pour que nose intercepte le
        # résultat
        assert self.lls.state.name.statename == u"UNKNOWN"

    @defer.inlineCallbacks
    def test_host_up(self):
        """Demander les états des services d'un hôte qui passe UP"""
        yield setup_context(
            self.rule._context_factory,
            self.message_id, {
                'statename': u"UP",
                'previous_state': tables.StateName.statename_to_value(u"DOWN"),
                'timestamp': 42,
                'hostname': "testhost",
                'servicename': None
        })
        yield self.rule.process(self.rule_runner, self.message_id, None)
        expected = NAGIOS_MESSAGE % {
            "ns": NS_COMMAND,
            "timestamp": 42,
            "host": "testhost"
        }
        expected = etree.fromstring(expected % {"svc": "testservice"})
        print "Received:", self.rule_runner.message
        result = etree.fromstring(self.rule_runner.message)
        result.find("{%s}timestamp" % NS_COMMAND).text = "42"
        assert etree.tostring(result) == etree.tostring(expected)

    @defer.inlineCallbacks
    def test_host_up_many_services(self):
        """Demander les états de tous les services d'un hôte qui passe UP"""
        yield setup_context(
            self.rule._context_factory,
            self.message_id, {
                'statename': u"UP",
                'previous_state': tables.StateName.statename_to_value(u"DOWN"),
                'timestamp': 42,
                'hostname': "testhost",
                'servicename': None
        })
        servicenames = [ u'testservice-%d' % i for i in range(10) ]
        for servicename in servicenames:
            DBSession.add(tables.LowLevelService(
                host=self.host,
                servicename=servicename,
                weight=42,
            ))
        DBSession.flush()
        rule_runner = Mock()
        yield self.rule.process(rule_runner, self.message_id, None)
        servicenames.insert(0, "testservice") # crée en setUp
        print rule_runner.callRemote.call_count
        assert rule_runner.callRemote.call_count == len(servicenames)
        for i, servicename in enumerate(servicenames):
            call = rule_runner.method_calls[i]
            print call
            assert call[0] == "callRemote"
            assert call[1] == (SendToBus, )
            assert call[2]["item"].count(servicename) == 1
