# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""Correlator Pubsub client."""
import threading, os, signal

from zope.interface import implements
from twisted.plugin import IPlugin
from twisted.application import service
from twisted.words.protocols.jabber.jid import JID
from twisted.internet import reactor

from vigilo.common.conf import settings
settings.load_module('vigilo.correlator')

from vigilo.common.logging import get_logger
LOGGER = get_logger('vigilo.correlator')

from vigilo.common.gettext import translate
_ = translate('vigilo.correlator')

from vigilo.connector import client, options
from vigilo.pubsub.checknode import VerificationNode
from vigilo.correlator.actors.rule_dispatcher import RuleDispatcher
from vigilo.common.conf import setup_plugins_path
from vigilo.correlator.memcached_connection import MemcachedConnection, \
                                                    MemcachedConnectionError
from vigilo.correlator.registry import get_registry


def log_debug_info(*args):
    LOGGER.debug('pid: %d', os.getpid())
    LOGGER.debug('threads: %s', threading.enumerate())

# Definit une routine pour le traitement
# du signal SIGHUP (rechargement).
def sighup_handler(*args):
    """Delete the topology associated with this context."""
    conn = MemcachedConnection()
    conn.delete('vigilo:topology')
    LOGGER.info(_(u"The topology has been reloaded."))

def set_signal_handlers():
    # Mise en place des routines de traitement des signaux.
    try:
        # Affiche des informations pour chaque processus
        # en cours d'exécution. Susceptible de faire
        # planter les processus d'exécution des règles.
        signal.signal(signal.SIGUSR1, log_debug_info)

        # Le signal SIGHUP servira à recharger la topologie
        # (utilisé par les scripts d'ini lors d'un reload).
        signal.signal(signal.SIGHUP, sighup_handler)
    except ValueError:
        LOGGER.error(_(u'Could not set signal handlers. The correlator '
                        'may not be able to shutdown cleanly'))


class CorrelatorServiceMaker(object):
    """
    Creates a service that wraps everything the correlator needs.
    """
    implements(service.IServiceMaker, IPlugin)
    tapname = "vigilo-correlator"
    description = "Vigilo correlator"
    options = options.Options

    def makeService(self, options):
        """Crée un service client du bus XMPP"""

        # Configuration de l'accès à la base de données.
        from vigilo.models.configure import configure_db
        configure_db(settings['database'], 'sqlalchemy_',
            settings['database']['db_basename'])

        # Enregistre les règles de corrélation dans le registre.
        # À LAISSER ABSOLUMENT.
        get_registry()

        setup_plugins_path(settings["correlator"].get("pluginsdir",
                           "/etc/vigilo/correlator/plugins"))

        reactor.addSystemEventTrigger('during', 'startup', set_signal_handlers)

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

        # Statistiques
        from vigilo.connector.status import StatusPublisher
        servicename = options["name"]
        if servicename is None:
            servicename = "vigilo-correlator"
        stats_publisher = StatusPublisher(msg_handler,
                        settings["connector"].get("hostname", None),
                        servicename=servicename,
                        node=settings["connector"].get("status_node", None))
        stats_publisher.setHandlerParent(xmpp_client)

        root_service = service.MultiService()
        xmpp_client.setServiceParent(root_service)
        return root_service

correlator = CorrelatorServiceMaker()
