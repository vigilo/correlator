# -*- coding: utf-8 -*-

import transaction
from twisted.protocols import amp

from vigilo.common.logging import get_logger
from vigilo.common.gettext import translate

from vigilo.correlator.amp import commands

LOGGER = get_logger(__name__)
_ = translate(__name__)

class Correlator(amp.AMP):
    def __init__(self):
        super(Correlator, self).__init__()

    @commands.SendToBus.responder
    def send_to_bus(self, item):
        LOGGER.debug(_('Sending this payload to the XMPP bus: %r'), item)
        self.rule_dispatcher.sendItem(item)
        return {}

    @commands.RegisterCallback.responder
    def register_callback(self, fn, idnt):
        LOGGER.debug(_('Registering post-correlation callback function '
                        '"%(fn)s" for alert with ID %(id)s'), {
                            'fn': fn,
                            'id': idnt,
                        })

        self.rule_dispatcher.tree_end.addCallback(fn, self.rule_dispatcher, self.database, idnt)
        return {}

