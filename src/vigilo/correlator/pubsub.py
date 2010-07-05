# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""
Correlator Pubsub client.
"""

from twisted.application import service
from twisted.words.protocols.jabber.jid import JID

from vigilo.connector.client import XMPPClient
from vigilo.pubsub.checknode import VerificationNode
from vigilo.correlator.actors.rule_dispatcher import RuleDispatcher

class CorrServiceMaker(object):
    """
    Creates a service that wraps everything the correlator needs.
    """

    #implements(service.IServiceMaker, IPlugin)

    def makeService(self):
        """Crée un service client du bus XMPP"""
        from vigilo.common.conf import settings

        try:
            require_tls = settings['bus'].as_bool('require_tls')
        except KeyError:
            require_tls = False

        xmpp_client = XMPPClient(
                JID(settings['bus']['jid']),
                settings['bus']['password'],
                settings['bus']['host'],
                require_tls=require_tls,
            )
        xmpp_client.setName('xmpp_client')

        try:
            xmpp_client.logTraffic = settings['bus'].as_bool('log_traffic')
        except KeyError:
            xmpp_client.logTraffic = False

        try:
            list_nodeOwner = settings['bus'].as_list('owned_topics')
        except KeyError:
            list_nodeOwner = []

        try:
            list_nodeSubscriber = settings['bus'].as_list('watched_topics')
        except KeyError:
            list_nodeSubscriber = []

        verifyNode = VerificationNode(list_nodeOwner, list_nodeSubscriber, 
                                      doThings=True)
        verifyNode.setHandlerParent(xmpp_client)

        _service = JID(settings['bus']['service'])
        nodetopublish = settings.get('publications', {})

        msg_handler = RuleDispatcher(
            settings['connector']['backup_file'],
            settings['connector']['backup_table_from_bus'],
            settings['connector']['backup_table_to_bus'],
            nodetopublish,
            _service
        )
        msg_handler.setHandlerParent(xmpp_client)

        root_service = service.MultiService()
        xmpp_client.setServiceParent(root_service)
        return root_service

