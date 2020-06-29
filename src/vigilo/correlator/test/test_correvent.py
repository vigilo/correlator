# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2020 CS GROUP – France
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

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
from vigilo.models.tables import Host, Event, CorrEvent, StateName
from vigilo.correlator.correvent import CorrEventBuilder
from vigilo.correlator.db_thread import DummyDatabaseWrapper

from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)



class TestCorrevents(unittest.TestCase):


    @deferred(timeout=60)
    def setUp(self):
        """Initialise MemcacheD et la BDD au début de chaque test."""
        super(TestCorrevents, self).setUp()
        helpers.setup_db()
        helpers.populate_statename()
        self.forwarder = helpers.RuleDispatcherStub()
        self.context_factory = helpers.ContextStubFactory()
        self.corrbuilder = CorrEventBuilder(Mock(), DummyDatabaseWrapper(True))
        self.corrbuilder.context_factory = self.context_factory
        self.make_deps()
        return defer.succeed(None)

    @deferred(timeout=60)
    def tearDown(self):
        """Nettoie MemcacheD et la BDD à la fin de chaque test."""
        super(TestCorrevents, self).tearDown()
        helpers.teardown_db()
        self.context_factory.reset()
        return defer.succeed(None)


    def make_deps(self):
        self.host = Host(
            name = u'Host',
            snmpcommunity = u'com11',
            hosttpl = u'tpl11',
            address = u'192.168.0.11',
            snmpport = 11,
        )
        DBSession.add(self.host)
        DBSession.flush()


    @deferred(timeout=60)
    @defer.inlineCallbacks
    def test_ignore_obsolete_updates(self):
        """
        On ignore les mises à jour avec données obsolètes sur un CorrEvent.
        """
        ts = time.time()
        ctx = self.context_factory(42)
        info_dictionary = {
            'id': 42,
            'timestamp': datetime.utcfromtimestamp(int(ts)),
            'host': self.host.name,
            'service': u'',
            'state': u'DOWN',
            'message': u'DOWN',
        }

        # Création Event + CorrEvent plus récent que
        # les informations portées par le message.
        new_ts = datetime.utcfromtimestamp(int(ts + 3600))
        event = Event(
            idsupitem=self.host.idhost,
            timestamp=new_ts,
            current_state=StateName.statename_to_value(u'UP'),
            message=u'UP',
        )
        DBSession.add(event)

        correvent = CorrEvent(
            cause=event,
            priority=42,
            trouble_ticket=None,
            ack=CorrEvent.ACK_NONE,
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
            ctx.set('timestamp', info_dictionary['timestamp']),
        ])

        # make_correvent NE DOIT PAS mettre à jour l'événement corrélé.
        # Il ne doit pas non plus y avoir création d'un nouvel événement
        # corrélé.
        res = yield self.corrbuilder.make_correvent(info_dictionary)

        LOGGER.debug('res = %r', res)
        self.assertEqual(None, res)
        LOGGER.debug('Checking the CorrEvent')
        db_correvent = DBSession.query(CorrEvent).one()
        self.assertEqual(db_correvent.idcorrevent, correvent.idcorrevent)
        LOGGER.debug('Checking the Event')
        db_event = DBSession.query(Event).one()
        self.assertEqual(db_event.idevent, event.idevent)
        state = StateName.value_to_statename(db_event.current_state)
        LOGGER.debug("Event's state: %r", state)
        self.assertEqual(u'UP', state)
        self.assertEqual(0,
                len(self.corrbuilder.publisher.sendMessage.call_args_list))
