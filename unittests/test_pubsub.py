# vim: set fileencoding=utf-8 sw=4 ts=4 et :
from __future__ import absolute_import

from twisted.trial import unittest
from twisted.internet.defer import succeed
from wokkel.test.helpers import TestableRequestHandlerMixin, XmlStreamStub

from vigilo.corr.pubsub import CorrServiceMaker

class NodeSubscriberTest(unittest.TestCase):
    timeout = 1
    def setUp(self):
        # Mocks the behaviour of XMPPClient. No TCP connections made.
        # A bit useless for integration tests;
        # we use high-level apis and need the real deal.
        self.stub = XmlStreamStub()
        self.protocol = CorrServiceMaker().makeService({})
        self.protocol.xmlstream = self.stub.xmlstream
        #self.protocol.connectionInitialized()



