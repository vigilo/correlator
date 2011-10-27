# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# pylint: disable-msg=C0111,W0212,R0904
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

""""""

import time
from datetime import datetime
import unittest

from nose.twistedtools import reactor, deferred
from twisted.internet import defer
from lxml import etree

from mock import Mock
import helpers
from vigilo.correlator.test.helpers import ContextStubFactory, \
                                            RuleDispatcherStub

from vigilo.pubsub.xml import NS_EVENT
from vigilo.models.session import DBSession
from vigilo.models.tables import Host, Event, CorrEvent, StateName
from vigilo.correlator.correvent import make_correvent
from vigilo.correlator.db_thread import DummyDatabaseWrapper

from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)

class TestCorrevents(unittest.TestCase):
    @deferred(timeout=30)
    def setUp(self):
        """Initialise MemcacheD et la BDD au début de chaque test."""
        super(TestCorrevents, self).setUp()
        helpers.setup_db()
        helpers.populate_statename()
        self.forwarder = RuleDispatcherStub()
        self.context_factory = ContextStubFactory()
        self.make_deps()
        return defer.succeed(None)

    @deferred(timeout=30)
    def tearDown(self):
        """Nettoie MemcacheD et la BDD à la fin de chaque test."""
        super(TestCorrevents, self).tearDown()
        helpers.teardown_db()
        return defer.succeed(None)

    def make_deps(self):
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

    @deferred(timeout=30)
    @defer.inlineCallbacks
    def test_ignore_obsolete_updates(self):
        """
        On ignore les mises à jour avec données obsolètes sur un CorrEvent.
        """
        ts = time.time()
        ctx = self.context_factory(42)
        info_dictionary = {
            'timestamp': ts,
            'host': self.host.name,
            'service': u'',
            'state': u'DOWN',
            'message': u'DOWN',
            'xmlns': NS_EVENT,
        }

        payload = """
<event xmlns="%(xmlns)s">
    <timestamp>%(timestamp)s</timestamp>
    <host>%(host)s</host>
    <service>%(service)s</service>
    <state>%(state)s</state>
    <message>%(state)s</message>
</event>
""" % info_dictionary
        item = etree.fromstring(payload)
        info_dictionary['timestamp'] = datetime.fromtimestamp(int(ts))

        # Création Event + CorrEvent plus récent que
        # les informations portées par le message.
        new_ts = datetime.fromtimestamp(int(ts + 3600))
        event = Event(
            idsupitem=self.host.idhost,
            timestamp=new_ts,
            current_state=StateName.statename_to_value(u'UP'),
            message=u'UP',
        )
        DBSession.add(event)

        correvent = CorrEvent(
            cause=event,
            impact=42,
            priority=42,
            trouble_ticket=None,
            status=u'None',
            occurrence=42,
            timestamp_active=new_ts,
        )
        DBSession.add(correvent)


        # On passe par une DeferredList pour garantir l'exécution
        # de tous les Deferred comme étant un seul bloc logique.
        yield defer.DeferredList([
            ctx.set('hostname', self.host.name),
            ctx.set('servicename', ''),
            ctx.set('statename', 'DOWN'),
            ctx.set('raw_event_id', event.idevent),
            ctx.set('idsupitem', self.host.idhost),
            ctx.set('payload', payload),
            ctx.set('timestamp', info_dictionary['timestamp']),
        ])

        # make_correvent NE DOIT PAS mettre à jour l'événement corrélé.
        # Il ne doit pas non plus y avoir création d'un nouvel événement
        # corrélé.
        res = yield make_correvent(
            self.forwarder,
            DummyDatabaseWrapper(True),
            item,
            42,
            info_dictionary,
            self.context_factory,
        )

        LOGGER.debug('res = %r', res)
        self.assertEquals(None, res)
        LOGGER.debug('Checking the CorrEvent')
        db_correvent = DBSession.query(CorrEvent).one()
        self.assertEquals(db_correvent.idcorrevent, correvent.idcorrevent)
        LOGGER.debug('Checking the Event')
        db_event = DBSession.query(Event).one()
        self.assertEquals(db_event.idevent, event.idevent)
        state = StateName.value_to_statename(db_event.current_state)
        LOGGER.debug("Event's state: %r", state)
        self.assertEquals(u'UP', state)
        defer.returnValue(None)
