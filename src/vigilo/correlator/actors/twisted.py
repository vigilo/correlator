# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""Module de lancement du réacteur de Twisted."""

from __future__ import absolute_import

from twisted.internet import reactor
from twisted.application import app, service

from vigilo.common.logging import get_logger
from vigilo.common.gettext import translate

LOGGER = get_logger(__name__)
_ = translate(__name__)

def main(manager):
    """Lancement du réacteur."""
    from vigilo.correlator.pubsub import CorrServiceMaker

    application = service.Application('Twisted PubSub component')
    corr_service = CorrServiceMaker().makeService({ 'manager': manager, })
    corr_service.setServiceParent(application)
    app.startApplication(application, False)

    reactor.run(installSignalHandlers=0)
    LOGGER.debug(_('Stopping the Twisted PubSub component'))
 
