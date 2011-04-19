# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""Module contenant divers fonctions outils d'aide pour les tests."""

import subprocess
import os
import signal
import time
import socket
import nose

from vigilo.common.conf import settings
settings.load_file('settings_tests.ini')

from vigilo.models.configure import configure_db
configure_db(settings['database'], 'sqlalchemy_')

from vigilo.models.session import metadata

from vigilo.correlator.memcached_connection import MemcachedConnection

MemcachedConnection.CONTEXT_TIMER = 0
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
    global mc_pid
    settings['correlator']['memcached_host'] = "127.0.0.1"
    port = get_available_port()
    settings['correlator']['memcached_port'] = port
    env = os.environ.copy()
    env["PATH"] += ":/usr/sbin" # Sur mandriva, memcached est dans /usr/sbin
    memcached_bin = None
    mc_pid = subprocess.Popen([settings['correlator']["memcached_command"],
                               "-l", "127.0.0.1",
                               "-p", str(port)],
                               env=env,
                               close_fds=True).pid
    # Give it time to start up properly. I should try a client connection in a
    # while loop. Oh well...
    time.sleep(1)
    # On s'assure qu'une connexion vers memcached est ouverte.
    MemcachedConnection()

def teardown_mc():
    """Détruit le serveur memcached créé pour le passage d'un test."""
    # Détruit l'objet qui gère la connexion.
    MemcachedConnection.reset()
    try:
        # Tue le serveur memcached lancé en arrière-plan.
        os.kill(mc_pid, signal.SIGTERM)
        os.wait() # Avoid zombies. Bad zombies.
    except OSError, e:
        print e
        pass # Ignore errors, maybe we should
             # do something more useful here.

with_mc = nose.with_setup(setup_mc, teardown_mc)


#Create an empty database before we start our tests for this module
def setup_db():
    """Crée toutes les tables du modèle dans la BDD."""
    from vigilo.models.tables.grouppath import GroupPath
    from vigilo.models.tables.usersupitem import UserSupItem
    tables = metadata.tables.copy()
    del tables[GroupPath.__tablename__]
    del tables[UserSupItem.__tablename__]
    metadata.create_all(tables=tables.itervalues())
    metadata.create_all(tables=[GroupPath.__table__, UserSupItem.__table__])

#Teardown that database
def teardown_db():
    """Supprime toutes les tables du modèle de la BDD."""
    metadata.drop_all()
