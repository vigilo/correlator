# vim: set fileencoding=utf-8 sw=4 ts=4 et :

import subprocess
import os
import signal
import time
import socket

from nose import with_setup

from vigilo.corr.conf import settings

mc_pid = None

def get_available_port():
    port = 11216
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    while port < 12000:
        try:
            s.bind(("localhost", port))
        except socket.error:
            port = port + 1
            continue
        break
    s.close()
    return port

def setup_mc():
    global mc_pid
    settings._Settings__dct['MEMCACHE_CONN_HOST'] = "localhost"
    port = get_available_port()
    settings._Settings__dct['MEMCACHE_CONN_PORT'] = port
    mc_pid = subprocess.Popen(["/usr/sbin/memcached",
                               "-l", "localhost",
                               "-p", str(port)],
                               close_fds=True).pid
    # Give it time to start up properly. I should try a client connection in a
    # while loop. Oh well...
    time.sleep(1)

def teardown_mc():
    global mc_pid
    os.kill(mc_pid, signal.SIGTERM)
    os.wait() # Avoid zombies. Bad zombies.

with_mc = with_setup(setup_mc, teardown_mc)

