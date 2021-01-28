# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2021 CS GROUP - France
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>
"""
Corrélateur de Vigilo.
"""

import threading
import os
import signal



def log_debug_info(*_args):
    from vigilo.common.logging import get_logger
    logger = get_logger(__name__)
    logger.debug('pid: %d', os.getpid())
    logger.debug('threads: %s', threading.enumerate())


def sighup_handler(*_args):
    """
    Definit une routine pour le traitement du signal SIGHUP (rechargement).
    """
    from vigilo.correlator.memcached_connection import MemcachedConnection
    from vigilo.common.logging import get_logger
    logger = get_logger(__name__)
    from vigilo.common.gettext import translate
    _ = translate(__name__)

    conn = MemcachedConnection()
    conn.delete('vigilo:topology')
    logger.info(_(u"The topology has been reloaded."))


def set_signal_handlers():
    from vigilo.common.logging import get_logger
    logger = get_logger(__name__)
    from vigilo.common.gettext import translate
    _ = translate(__name__)

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
        logger.error(_(u'Could not set signal handlers. The correlator '
                        'may not be able to shutdown cleanly'))



def makeService(options):
    """Crée un service client du bus"""
    from vigilo.connector.options import getSettings
    settings = getSettings(options, __name__)

    from twisted.internet import reactor
    from twisted.application import service

    # Configuration de l'accès à la base de données.
    from vigilo.correlator.db_thread import DatabaseWrapper
    database = DatabaseWrapper(settings['database'])

    from vigilo.common.conf import setup_plugins_path
    from vigilo.connector.client import client_factory
    from vigilo.correlator.actors.rule_dispatcher import ruledispatcher_factory

    # Enregistre les règles de corrélation dans le registre.
    # À LAISSER ABSOLUMENT.
    from vigilo.correlator.registry import get_registry
    get_registry()

    setup_plugins_path(settings["correlator"].get("pluginsdir",
                       "/etc/vigilo/correlator/plugins"))

    reactor.addSystemEventTrigger('during', 'startup', set_signal_handlers)
    reactor.addSystemEventTrigger('before', 'shutdown', database.shutdown)

    root_service = service.MultiService()

    # Client du bus
    client = client_factory(settings)
    client.setServiceParent(root_service)

    # Réceptionneur de messages
    msg_handler = ruledispatcher_factory(settings, database, client)

    # Statistiques
    # Seule la première instance du corrélateur est permanente.
    idinstance = str(settings.get("instance", "") or 1)
    if idinstance == "1":
        from vigilo.connector.status import statuspublisher_factory
        statuspublisher_factory(settings, client, providers=(msg_handler,))

    return root_service
