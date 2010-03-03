# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""
Module de lancement du corrélateur.
"""

from __future__ import with_statement

def main_cmdline(*args):
    """Fonction appelée au lancement du corrélateur."""
    from vigilo.common.daemonize import daemonize

    with daemonize():
        from vigilo.common.conf import settings
        settings.load_module(__name__)
        from vigilo.correlator.connect import connect
        from vigilo.common.gettext import translate
        from vigilo.common.logging import get_logger

        LOGGER = get_logger(__name__)
        _ = translate(__name__)


        # On tente d'établir une connexion au serveur memcached
        # et d'enregistrer une clé dedans. Teste la connectivité.
        mc_conn = connect()
        if not mc_conn.set('vigilo', '', 1):
            LOGGER.critical(_("Could not connect to memcached server, "
                                "make sure it is running"))
            return 1

        from vigilo.correlator.actors.start import start
        return start()

if __name__ == '__main__':
    sys.exit(main_cmdline())

