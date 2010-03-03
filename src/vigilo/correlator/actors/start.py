# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""
Module de lancement du corrélateur.
"""
from __future__ import absolute_import

import os
import signal
import sys
import errno

from vigilo.common.conf import settings
settings.load_module(__name__)

from twisted.internet import reactor

from vigilo.correlator.actors.pool import VigiloProcess
from vigilo.correlator.libs import mp

from vigilo.common.gettext import translate
from vigilo.common.logging import get_logger

LOGGER = get_logger(__name__)
_ = translate(__name__)

manager = None

def log_debug_info(*args):
    import threading
    LOGGER.debug('pid: %d' % os.getpid())
    LOGGER.debug('children: %s' % mp.active_children())
    LOGGER.debug('threads: %s' % threading.enumerate())

# Definit une routine pour le traitement
# du signal SIGHUP (rechargement).
def sighup_handler(*args):
    """Delete the topology associated with this context."""
    from vigilo.correlator.context import TOPOLOGY_PREFIX
    from vigilo.correlator.connect import connect

    conn = connect()
    conn.delete(TOPOLOGY_PREFIX)
    LOGGER.info(_("The topology has been reloaded."))


def start():
    """Fonction principale de lancement du corrélateur."""
    from vigilo.common.conf import settings
    from vigilo.correlator.registry import get_registry
    from vigilo.models.configure import configure_db
    from vigilo.correlator.actors import twisted, rule_dispatcher

    global manager

    # Enregistre les règles de corrélation dans le registre.
    # À LAISSER ABSOLUMENT.
    get_registry()

    # Configuration de l'accès à la base de données.
    configure_db(settings['database'], 'sqlalchemy_')

    # Création d'un manager de ressources pour le partage
    # des files de données entre les processus.
    manager = mp.Manager()

    # Création des files pour les échanges de données.
    try:
        queue_size = settings['correlator'].as_int('queue_size')
    except KeyError:
        manager.in_queue = mp.Queue()
        manager.out_queue = mp.Queue()
    else:
        manager.in_queue = mp.Queue(queue_size)
        manager.out_queue = mp.Queue(queue_size)

    def sigterm_handler(signum, stack):
        from twisted.internet import reactor
        signal.signal(signum, signal.SIG_IGN)

        LOGGER.debug(_('Asking the Rule dispatcher to gracefully exit.'))
        manager.in_queue.put(None)

        LOGGER.debug(_('Sending shutdown message to QueueToNodeForwarder.'))
        manager.out_queue.put(None)

        reactor.stop()

    rrp = mp.Process(name='Rule dispatcher',
            target=rule_dispatcher.main, args=(manager, ))

    # Mise en place des routines de traitement des signaux.
    try:
        # Affiche des informations pour chaque processus
        # en cours d'exécution. Susceptible de faire
        # planter les processus d'exécution des règles.
        signal.signal(signal.SIGUSR1, log_debug_info)

        # Le signal SIGHUP servira à recharger la topologie
        # (utilisé par les scripts d'ini lors d'un reload).
        signal.signal(signal.SIGHUP, sighup_handler)

        # Chacun de ces signaux peut être utilisé pour
        # demander l'arrêt du corrélateur.
        # Par défaut, kill(1) envoie un signal SIGINT.
        # Depuis le scripts d'init, on envoie SIGTERM.
        # Si utilisé avec un pipe, on recevra SIGPIPE.
        signal.signal(signal.SIGINT, sigterm_handler)
        signal.signal(signal.SIGTERM, sigterm_handler)
        signal.signal(signal.SIGPIPE, sigterm_handler)
    except ValueError:
        LOGGER.error(_('Could not set signal handlers. The correlator '
                        'may not be able to shutdown cleanly'))

    rrp.start()
    twisted.main(manager)

    # On laisse quelques secondes au processus pour s'arrêter proprement.
    rrp.join(timeout=5.0)
    if rrp.is_alive():
        rrp.terminate()
        rrp.join()
        LOGGER.debug(_('Terminated the Rule dispatcher'))
    else:
        LOGGER.debug(_("Joined with the Rule dispatcher"))

    # On détruit les files, ainsi que le manager.
    manager.in_queue.close()
    manager.out_queue.close()
    manager.shutdown()

    LOGGER.debug(_('Stopping the main process.'))

    try:
        os.waitpid(0, -1)
    except OSError:
        pass

