# vim: set fileencoding=utf-8 sw=4 ts=4 et :
from __future__ import absolute_import

import Queue as queue

# trial seems a more featureful option than nose's twisted plugin
from twisted.trial import unittest

from twisted.internet import reactor, task
from twisted.internet.defer import succeed
from wokkel import client, pubsub
from wokkel.test.helpers import TestableRequestHandlerMixin, XmlStreamStub

from vigilo.common.pubsub import NodeOwner
from vigilo.corr.conf import settings
from vigilo.corr.pubsub import CorrServiceMaker

class NodeSubscriberTest(unittest.TestCase):
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
                settings['XMPP_SERVER_HOST'])
        node_owner = NodeOwner()
        node_owner.setHandlerParent(self.xmpp_client)
        self.xmpp_client.startService()
        # Wait a few seconds so the connection is done.
        # We have no way to get a deferred for startService.
        return task.deferLater(reactor, 1., lambda: None)

    def tearDown(self):
        return self.xmpp_client.stopService()

    def testConnected(self):
        pass

class CorrServiceTest(unittest.TestCase):
    timeout = 2

    def setUp(self):
        class mock_manager(object): pass
        self.manager = mock_manager()
        self.manager.alert_msgs_queue = queue.Queue()
        self.manager.agg_msgs_queue = queue.Queue()
        self.corr_client = CorrServiceMaker().makeService({'manager': self.manager, })
        # Blocks badly
        #self.corr_client.startService()
        # Wait a few seconds so the connection is done.
        # We have no way to get a deferred for startService.
        return task.deferLater(reactor, 1., lambda: None)

    def tearDown(self):
        return self.corr_client.stopService()


