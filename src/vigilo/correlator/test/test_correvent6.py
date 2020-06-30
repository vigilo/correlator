# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2020 CS GROUP - France
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""

"""

# pylint: disable-msg=C0111,W0212,R0904,W0201
# - C0111: Missing docstring
# - W0212: Access to a protected member of a client class
# - R0904: Too many public methods
# - W0201: Attribute defined outside __init__


import time
from datetime import datetime
import unittest

from nose.twistedtools import reactor  # pylint: disable-msg=W0611
from nose.twistedtools import deferred

from twisted.internet import defer

from mock import Mock
from vigilo.correlator.test import helpers

from vigilo.models.session import DBSession
from vigilo.models.demo import functions
from vigilo.models import tables
from vigilo.correlator.correvent import CorrEventBuilder
from vigilo.correlator.db_thread import DummyDatabaseWrapper

from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)


class TestCorrevents6(unittest.TestCase):
    @deferred(timeout=60)
    def setUp(self):
        """Initialise la BDD au début de chaque test."""
        super(TestCorrevents6, self).setUp()
        helpers.setup_db()
        helpers.populate_statename()
        self.forwarder = helpers.RuleDispatcherStub()
        self.context_factory = helpers.ContextStubFactory()
        self.corrbuilder = CorrEventBuilder(Mock(), DummyDatabaseWrapper(True))
        self.corrbuilder.context_factory = self.context_factory
        self.hosts = {
            1: functions.add_host(u'Host 1'),
            2: functions.add_host(u'Host 2'),
            3: functions.add_host(u'Host 3'),
        }
        return defer.succeed(None)

    @deferred(timeout=60)
    def tearDown(self):
        """Nettoie la BDD à la fin de chaque test."""
        super(TestCorrevents6, self).tearDown()
        helpers.teardown_db()
        self.context_factory.reset()
        return defer.succeed(None)


    @deferred(timeout=60)
    @defer.inlineCallbacks
    def test_no_predecessors(self):
        """Agrégation topologique : pas de prédécesseurs."""
        ctx = self.context_factory(42)
        event1 = functions.add_event(self.hosts[1], 'DOWN', u'foo')
        ctx.set('predecessors_aggregates', [])
        res = yield self.corrbuilder._aggregate_topologically(
                    ctx, None, event1.idevent, self.hosts[1].idhost)
        self.assertEqual(False, res)


    @deferred(timeout=60)
    @defer.inlineCallbacks
    def test_predecessor_and_no_aggregate(self):
        """Agrégation topologique : prédécesseur et pas d'agrégat."""
        ctx = self.context_factory(42)
        event1 = functions.add_event(self.hosts[1], 'DOWN', u'foo')
        event2 = functions.add_event(self.hosts[2], 'UNREACHABLE', u'foo')
        aggr1 = functions.add_correvent([event1])
        ctx.set('predecessors_aggregates', [aggr1.idcorrevent])
        ctx.set('successors_aggregates', [])
        res = yield self.corrbuilder._aggregate_topologically(
                    ctx, None, event2.idevent, self.hosts[2].idhost)
        self.assertEqual(True, res)
        self.assertEqual(1, DBSession.query(tables.CorrEvent).count())
        self.assertEqual(2, DBSession.query(tables.Event).count())


    @deferred(timeout=60)
    @defer.inlineCallbacks
    def test_nonexisting_predecessor(self):
        """Agrégation topologique : agrégat inexistant."""
        ctx = self.context_factory(42)
        event1 = functions.add_event(self.hosts[1], 'DOWN', u'foo')
        event2 = functions.add_event(self.hosts[2], 'UNREACHABLE', u'foo')
        ctx.set('predecessors_aggregates', [1])
        res = yield self.corrbuilder._aggregate_topologically(
                    ctx, None, event2.idevent, self.hosts[2].idhost)
        self.assertEqual(False, res)
        self.assertEqual(0, DBSession.query(tables.CorrEvent).count())
        self.assertEqual(2, DBSession.query(tables.Event).count())


    @deferred(timeout=60)
    @defer.inlineCallbacks
    def test_predecessor_and_aggregate(self):
        """Agrégation topologique : totale."""
        ctx = self.context_factory(42)
        event1 = functions.add_event(self.hosts[1], 'DOWN', u'foo')
        event2 = functions.add_event(self.hosts[2], 'UNREACHABLE', u'foo')
        event3 = functions.add_event(self.hosts[3], 'UNREACHABLE', u'foo')
        aggr1 = functions.add_correvent([event1])
        aggr2 = functions.add_correvent([event2])
        aggr3 = functions.add_correvent([event3])
        ctx.set('predecessors_aggregates', [aggr1.idcorrevent])
        ctx.set('successors_aggregates', [aggr3.idcorrevent])
        res = yield self.corrbuilder._aggregate_topologically(
                    ctx, aggr2, event2.idevent, self.hosts[2].idhost)
        self.assertEqual(True, res)
        self.assertEqual(1, DBSession.query(tables.CorrEvent).count())
        self.assertEqual(3, DBSession.query(tables.Event).count())

