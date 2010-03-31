#!/usr/bin/twistd -ny
# -*- coding: utf-8 -*-
# vim: set ft=python fileencoding=utf-8 sw=4 ts=4 et :
"""
A bit of glue, you can start this with twistd -ny path/to/file.py
"""
import sys
import signal

from twisted.internet import reactor
from twisted.application import service

# Lorsque twistd exécute le code du module,
# __name__ vaut "__builtins__", d'où l'utilisation
# d'une valeur explicite dans les settings, etc.
from vigilo.common.conf import settings
settings.load_module('vigilo.correlator')

from vigilo.common.gettext import translate
from vigilo.common.logging import get_logger

LOGGER = get_logger('vigilo.correlator')
_ = translate('vigilo.correlator')

# Configuration de l'accès à la base de données.
from vigilo.models.configure import configure_db
configure_db(settings['database'], 'sqlalchemy_',
    settings['database']['db_basename'])

from vigilo.correlator.context import TOPOLOGY_PREFIX
from vigilo.correlator.memcached_connection import MemcachedConnection, \
                                                    MemcachedConnectionError
from vigilo.correlator.registry import get_registry
from vigilo.correlator.pubsub import CorrServiceMaker

# On tente d'établir une connexion au serveur memcached
# et d'enregistrer une clé dedans. Teste la connectivité.
mc_conn = MemcachedConnection()
try:
    mc_conn.set('vigilo', '', 1)
except MemcachedConnectionError:
    # Inutile de logger un message ici, la classe
    # MemcachedConnection le fait déjà.
    sys.exit(1)


# Enregistre les règles de corrélation dans le registre.
# À LAISSER ABSOLUMENT.
get_registry()

def log_debug_info(*args):
    import threading, os
    LOGGER.debug('pid: %d' % os.getpid())
    LOGGER.debug('threads: %s' % threading.enumerate())

# Definit une routine pour le traitement
# du signal SIGHUP (rechargement).
def sighup_handler(*args):
    """Delete the topology associated with this context."""
    conn = MemcachedConnection()
    conn.delete(TOPOLOGY_PREFIX)
    LOGGER.info(_("The topology has been reloaded."))

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
        LOGGER.error(_('Could not set signal handlers. The correlator '
                        'may not be able to shutdown cleanly'))

reactor.addSystemEventTrigger('during', 'startup', set_signal_handlers)

application = service.Application('Twisted PubSub component')
corr_service = CorrServiceMaker().makeService()
corr_service.setServiceParent(application)

