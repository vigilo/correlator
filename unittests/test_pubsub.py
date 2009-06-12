# vim: set fileencoding=utf-8 sw=4 ts=4 et :
from __future__ import absolute_import

import Queue as queue
import random
import threading
import time

# trial seems a more featureful option than nose's twisted plugin
# OTOH, it is much less convenient, especially since the reactor
# is stopped during tests.
if True:
    from twisted.trial import unittest
    from twisted.internet import reactor
    unittest.TestCase.timeout = 2
else:
    import unittest
    from nose.twistedtools import reactor, deferred

from twisted.internet import task
from twisted.internet.base import DelayedCall
from twisted.internet.defer import Deferred, inlineCallbacks, succeed
from twisted.internet.threads import deferToThread
from twisted.words.xish import domish
from wokkel import client, pubsub, subprotocols
from wokkel.generic import parseXml
from wokkel.test.helpers import TestableRequestHandlerMixin, XmlStreamStub

from vigilo.common.logging import get_logger
from vigilo.common.pubsub import (
        NodeOwner, NodeToQueueForwarder, QueueToNodeForwarder, Subscription, )
from vigilo.corr.conf import settings
from vigilo.corr.pubsub import CorrServiceMaker

LOGGER = get_logger(__name__)

test_sub = Subscription(
        settings['XMPP_PUBSUB_SERVICE'],
        settings['VIGILO_TESTALERTS_TOPIC'] + '/' + str(random.random()),
        )

DelayedCall.debug = True

class XmppClient(unittest.TestCase):
    timeout = 2

    def setUp(self):
        # Mocks the behaviour of XMPPClient. No TCP connections made.
        # A bit useless for integration tests;
        # we use high-level apis and need the real deal.
        if False:
            self.stub = XmlStreamStub()
            self.protocol.xmlstream = self.stub.xmlstream
            self.protocol.connectionInitialized()

        self.xmpp_client = client.XMPPClient(
                settings['VIGILO_CORR_JID'],
                settings['VIGILO_CORR_PASS'],
                settings['XMPP_SERVER_HOST'],
                )
        #self.xmpp_client.logTraffic = True
        self.xmpp_client.startService()
        node_owner = NodeOwner()
        node_owner.setHandlerParent(self.xmpp_client)
        self.test_sub = test_sub.subscription_with_owner(node_owner)

        conn_deferred = Deferred()
        conn_handler = subprotocols.XMPPHandler()
        def on_conn():
            reactor.callLater(1., lambda: conn_deferred.callback(None))
        conn_handler.connectionInitialized = on_conn
        conn_handler.setHandlerParent(self.xmpp_client)

        # Wait a few seconds so the xml stream is established.
        # This allows us to use shorter timeouts later.
        # We have no way to get a deferred for startService,
        # which would have been quicker.
        #return deferToThread(lambda: time.sleep(1.5))
        #return task.deferLater(reactor, 1., lambda: None)
        return conn_deferred

    def tearDown(self):
        return self.xmpp_client.stopService()

    @inlineCallbacks
    def testForwarders(self):
        in_queue = queue.Queue()
        out_queue = queue.Queue()
        ntqf = NodeToQueueForwarder(self.test_sub, out_queue)
        ntqf.setHandlerParent(self.xmpp_client)
        qtnf = QueueToNodeForwarder(in_queue, self.test_sub)
        qtnf.setHandlerParent(self.xmpp_client)

        cookie = str(random.random())
        dom = domish.Element(('vigilo', 'test', ))
        dom['cookie'] = cookie
        item = pubsub.Item(payload=dom)
        in_queue.put_nowait(item.toXml())
        out_xml = (yield deferToThread(lambda: out_queue.get(timeout=1.4)))
        item = parseXml(out_xml)
        assert item.children[0]['cookie'] == cookie
        assert item.children[0].toXml() == dom.toXml()

        ntqf.disownHandlerParent(self.xmpp_client)
        qtnf.disownHandlerParent(self.xmpp_client)


#class CorrService(unittest.TestCase):
class CorrService(object):
    """
    This test has an Heisenbug.

    Depends on the test runner (trial or nose), the logging,
    and, if nose is used, whether coverage is used.

    inlineCallbacks gives the wrong backtrace, use trial's debug options to
    drop into pdb and get inlineCallbacks's deferred and the real backtrace.
    print deferred._debugInfo._getDebugTracebacks()

    Apparently the connection is found dropped in the connectionInitialized
    handlers.
    """

    timeout = 2

    def setUp(self):
        class mock_manager(object): pass
        self.manager = mock_manager()
        self.manager.alert_msgs_queue = queue.Queue()
        self.manager.agg_msgs_queue = queue.Queue()
        self.corr_client = CorrServiceMaker().makeService(
                {'manager': self.manager, })
        self.corr_client.startService()
        self.xmpp_client = self.corr_client.getServiceNamed('xmpp_client')
        # Wait a few seconds so the connection is done.
        # We have no way to get a deferred for startService.
        return task.deferLater(reactor, 1.5, lambda: None)

    def tearDown(self):
        print threading.enumerate()
        return self.corr_client.stopService()
        pass

    def testFoo(self):
        pass


