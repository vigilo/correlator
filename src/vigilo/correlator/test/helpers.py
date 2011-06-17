# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Classes et fonctions pour aider aux tests unitaires
"""

import subprocess
import os
import signal
import time
import socket
import nose

from twisted.internet import defer

from vigilo.common.conf import settings
settings.load_file('settings_tests.ini')

from vigilo.models.configure import configure_db
configure_db(settings['database'], 'sqlalchemy_')

from vigilo.models.session import metadata, DBSession
from vigilo.models.tables import StateName

from vigilo.correlator.context import Context
from vigilo.correlator.memcached_connection import MemcachedConnection
from vigilo.correlator.db_thread import DummyDatabaseWrapper

MemcachedConnection.CONTEXT_TIMER = 0


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

mc_pid = None
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
    MemcachedConnection(DummyDatabaseWrapper(True))

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
class ConnectionStub(object):
    def __init__(self):
        self.data = {}

    def get(self, key, transaction=True):
        print "GETTING: %r = %r" % (key, self.data.get(key))
        return self.data.get(key)

    def set(self, key, value, transaction=True, **kwargs):
        self.data[key] = value

    def delete(self, key, transaction=True):
        del self.data[key]


# Mocks
class ContextStub(Context):
    def __init__(self, idxmpp, timeout=None):
        self._connection = ConnectionStub()
        self._id = str(idxmpp)
        if timeout is None:
            timeout = 60.0
        self._timeout = timeout
        self._transaction = False
        self._database = DummyDatabaseWrapper(True)

class ContextStubFactory(object):
    def __init__(self):
        self.contexts = {}

    def __call__(self, idxmpp, timeout=None, *args, **kwargs):
        if idxmpp not in self.contexts:
            print "CREATING CONTEXT FOR", idxmpp
            self.contexts[idxmpp] = ContextStub(idxmpp, timeout)
        else:
            print "GETTING PREVIOUS CONTEXT FOR", idxmpp
        return self.contexts[idxmpp]


class RuleRunnerStub(object):
    """
    Classe simulant le fonctionnement du RuleRunner,
    pour intercepter les messages générés par la règle.
    """
    def __init__(self):
        """Initialisation"""
        self.message = None
    def callRemote(self, *args, **kwargs): # pylint: disable-msg=W0613
        """Méthode appelée par la règle pour envoyer le message sur le bus"""
        if 'item' in kwargs:
            self.message = kwargs['item']
    def clearMessage(self):
        """Suppression du message stocké"""
        self.message = None

@defer.inlineCallbacks
def setup_context(factory, message_id, context_keys):
    """
    Crée un contexte et l'initialise avec les données
    extraites du message, comme le ferait le rule_dispatcher.

    @param factory: Factory générant les contextes.
    @type  factory: C{ContextStubFactory}
    @param message_id: Identifiant du message dont on crée le contexte.
    @type  message_id: C{int}
    @param context_keys: Dictionnaire des clés à insérer dans le contexte.
    @type  context_keys: C{dict} of C{basestring}
    """
    ctx = factory(message_id)
    for key in context_keys:
        yield ctx.set(key, context_keys[key])

def get_context_key(factory, message_id, key):
    ctx = factory(message_id)
    return ctx.get(key)

def populate_statename():
    """ Remplissage de la table StateName """
    DBSession.add(StateName(statename=u'OK', order=0))
    DBSession.add(StateName(statename=u'UNKNOWN', order=1))
    DBSession.add(StateName(statename=u'WARNING', order=2))
    DBSession.add(StateName(statename=u'CRITICAL', order=3))
    DBSession.add(StateName(statename=u'UP', order=0))
    DBSession.add(StateName(statename=u'DOWN', order=3))
    DBSession.add(StateName(statename=u'UNREACHABLE', order=1))
    DBSession.flush()

