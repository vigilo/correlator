# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""
Correlator Pubsub client.
"""

from twisted.application import service
from twisted.words.protocols.jabber.jid import JID

from vigilo.connector import client
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

        xmpp_client = client.client_factory(settings)

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
