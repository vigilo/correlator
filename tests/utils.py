# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""Module contenant divers fonctions outils d'aide pour les tests."""

import subprocess
import os
import signal
import time
import socket
import sys
import nose

from vigilo.common.conf import settings
settings.load_module(__name__)
from vigilo.models.configure import metadata, DBSession, configure_db

mc_pid = None

def get_available_port():
    """
    Obtient le numéro d'un port disponible sur la machine.
    Le port retourné est tel que 11216 <= port < 12000.
    """
    port = 11216
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    while port < 12000:
        try:
            s.bind(("127.0.0.1", port))
        except socket.error:
            port = port + 1
            continue
        break
    s.close()
    return port

def setup_mc():
    """Lance un serveur memcached pour les tests."""
    from vigilo.common.conf import settings

    global mc_pid
    settings['correlator']['memcached_host'] = "127.0.0.1"
    port = get_available_port()
    settings['correlator']['memcached_port'] = port
    mc_pid = subprocess.Popen([settings['correlator']["memcached_command"],
                               "-l", "127.0.0.1",
                               "-p", str(port)],
                               close_fds=True).pid
    # Give it time to start up properly. I should try a client connection in a
    # while loop. Oh well...
    time.sleep(1)

def teardown_mc():
    """Détruit le serveur memcached créé pour le passage d'un test."""
    try:
        os.kill(mc_pid, signal.SIGTERM)
        os.wait() # Avoid zombies. Bad zombies.
    except OSError:
        pass # Ignore errors, maybe we should
             # do something more useful here.

with_mc = nose.with_setup(setup_mc, teardown_mc)


#Create an empty database before we start our tests for this module
def setup_db():
    """Crée toutes les tables du modèle dans la BDD."""
    from vigilo.common.conf import settings

    configure_db(settings['correlator'], 'sqlalchemy_')
    metadata.create_all()
    
#Teardown that database 
def teardown_db():
    """Supprime toutes les tables du modèle de la BDD."""
    metadata.drop_all()

