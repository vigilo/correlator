# vim: set fileencoding=utf-8 sw=4 ts=4 et :
from __future__ import absolute_import

from twisted.trial import unittest
from twisted.internet.defer import succeed
from wokkel.test.helpers import TestableRequestHandlerMixin, XmlStreamStub

from vigilo.common.pubsub import NodeSubscriber, Subscription
from vigilo.corr.pubsub import CorrClient, XMPP_PUBSUB_SERVICE

TEST_ALERTS_TOPIC = '/home/localhost/correlator/test/alerts'

class NodeSubscriberTest(unittest.TestCase):
    timeout = 1
    def setUp(self):
        alerts_sub = Subscription(XMPP_PUBSUB_SERVICE, TEST_ALERTS_TOPIC)
        # Mocks the behaviour of XMPPClient. No TCP connections made.
        # A bit useless for integration tests;
        # we use high-level apis and need the real deal.
        self.stub = XmlStreamStub()
        self.protocol = NodeSubscriber([alerts_sub])
        self.protocol.xmlstream = self.stub.xmlstream
        #self.protocol.connectionInitialized()



