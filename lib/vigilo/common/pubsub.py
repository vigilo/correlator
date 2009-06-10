# vim: set fileencoding=utf-8 sw=4 ts=4 et :
from __future__ import absolute_import

"""
Extensible pubsub clients to manage topic nodes.
"""

from twisted.internet import defer, reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.words.protocols.jabber import error
from wokkel import pubsub, xmppim
from wokkel.generic import parseXml

from vigilo.common.logging import get_logger

LOGGER = get_logger(__name__)

class Subscription(object):
    """
    Describe a subscription to something (but not a subscription of someone).

    Composed of a pubsub service (generally pubsub.server.tld),
    a node id, and an optional node owner thet implements L{NodeOwner}.
    """

    def __init__(self, service, node, owner=None):
        self.__service = service
        self.__node = node
        self.__owner = owner

    @property
    def service(self):
        return self.__service

    @property
    def node(self):
        return self.__node

    @property
    def owner(self):
        return self.__owner

    def subscription_with_owner(owner):
        # Maybe the topic (owner-less) / subscription (owner)
        # thing could be handled with a zope.interfaces style adapt.
        return Subscription(self.service, self.node, owner)

class NodeOwner(pubsub.PubSubClient):
    """
    A pubsub client able to own (create and manage) nodes.
    """

    @inlineCallbacks
    def ensureTopicNode(self, service_id, name):
        """
        Ensure a topic node exists.

        Assumes ejabberd. ejabberd needs us to create parents
        before children, and returns a <forbidden/> otherwise.
        """

        @inlineCallbacks
        def ensure(name):
            # Had to patch wokkel: http://wokkel.ik.nu/ticket/49
            # Edit: the patch isn't necessary anymore,
            # since the mdv 2009.0 -> 2009.1 upgrade
            # http://process-one.net/en/ejabberd/release_notes/release_note_ejabberd_2.0.4/
            # PubSub: Allow node creation without configure item
            try:
                yield self.createNode(service_id, name)
                returnValue(True)
            except error.StanzaError, se:
                if se.condition == 'conflict':
                    # We tried to create a node that exists.
                    # This is the desired outcome.
                    returnValue(True)
                elif se.condition == 'forbidden':
                    # ejabberd's way of saying "create parent first"
                    returnValue(False)
                else:
                    raise
        # pylint/astng cannot deal
        # http://www.logilab.org/ticket/8771
        # was supposed to fix this in hg, but hasn't.
        # (and btw, unrelated: http://www.logilab.org/ticket/5010 )
        if (yield ensure(name)):
            return
        components = [ e for e in name.split('/') if e != '' ]
        # parent_paths is like [ '/a', '/a/b', … ]
        parent_paths = reduce(lambda x, y: x + [ x[-1] + '/' + y, ],
                components, [''])[1:]
        # Path creation sent in order (xmpp is tcp-based).
        # DeferredList waits for all creations to be confirmed.
        yield defer.DeferredList([ensure(path) for path in parent_paths])


class NodeSubscriber(pubsub.PubSubClient):
    """
    A pubsub consumer, able to subscribe to topic nodes.

    You'll probably want to override itemsReceived.

    Some examples:
    http://www.google.com/codesearch?q=PubSubClient+itemsReceived
    """

    def __init__(self, subscriptions):
        """
        Create a pubsub subscriber.

        subscriptions is a list of L{Subscription}s to subscribe to.
        """

        super(NodeSubscriber, self).__init__()
        self.__subscriptions = subscriptions

    def connectionInitialized(self):
        # Called when we are connected and authenticated
        super(NodeSubscriber, self).connectionInitialized()

        # There's probably a way to configure it (on_sub vs on_sub_and_presence)
        # but the spec defaults to not sending subscriptions without presence.
        self.send(xmppim.AvailablePresence())

        return defer.DeferredList([
                self.ensureSubscribed(subscription)
                for subscription in self.__subscriptions])

    @inlineCallbacks
    def ensureSubscribed(self, subscription):
        """
        Ensure we are subscribed to the subscription.

        If the subscription has a node owner,
        we ask it to ensure the node exists.
        """

        # Complicated, due to things like SASL anonymous.
        # See http://wokkel.ik.nu/ticket/18
        my_jid = self.parent.factory.authenticator.jid

        # userhostJID is to avoid the resource part:
        # subscribing with multiple resources gives us multiple notifications,
        # and wokkel makes no attempt to filter them.
        my_jid = my_jid.userhostJID()

        if subscription.owner is not None:
            yield subscription.owner.ensureTopicNode(
                    subscription.service, subscription.node)
        yield self.subscribe(subscription.service, subscription.node, my_jid)
        LOGGER.info('subscribed')


class QueueToNodeForwarder(pubsub.PubSubClient):
    """
    Publishes pubsub items from a queue.

    Consumes serialized xml payloads from a L{Queue.Queue}
    and publishes to a pubsub topic node.
    """

    def __init__(self, queue, subscription):
        self.__queue = queue
        self.__subscription = subscription

    def consumeQueue(self):
        # Isn't there a callInThread / callFromThread decorator?
        while True:
            # blocks, doesn't time out
            xml = self.__queue.get(block=True, timeout=None)
            # Parsing is thread safe I expect
            dom = parseXml(xml)
            item = pubsub.Item(payload=dom)
            # XXX Connection loss might be problematic
            reactor.callFromThread(self.publish,
                    self.__subscription.service,
                    self.__subscription.node,
                    [dom])

    def connectionInitialized(self):
        reactor.callInThread(self.consumeQueue)


class NodeToQueueForwarder(NodeSubscriber):
    """
    Receives messages on the xmpp bus, and passes them to rule processing.
    """

    def __init__(self, subscription, queue):
        self.__queue = queue
        NodeSubscriber.__init__(self, [subscription])

    def itemsReceived(self, event):
        # See ItemsEvent
        #event.sender
        #event.recipient
        #event.nodeIdentifier
        #event.headers
        for item in event.items:
            # Item is a domish.IElement and a domish.Element
            # Serialize as XML before queueing,
            # or we get harmless stderr pollution  × 5 lines:
            # Exception RuntimeError: 'maximum recursion depth exceeded in __subclasscheck__' in <type 'exceptions.AttributeError'> ignored
            # Stderr pollution caused by http://bugs.python.org/issue5508
            # and some touchiness on domish attribute access.
            xml = item.toXml()
            LOGGER.debug('Got item: %s', xml)
            if item.name != 'item':
                # The alternative is 'retract', which we silently ignore
                # We receive retractations in FIFO order,
                # ejabberd keeps 10 items before retracting old items.
                continue
            # Might overflow the queue, but I don't think we are
            # allowed to block.
            self.__queue.put_nowait(xml)

