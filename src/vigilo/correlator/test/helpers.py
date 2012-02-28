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

from twisted.internet import defer, reactor
from mock import Mock

from vigilo.common.conf import settings
settings.load_file('settings_tests.ini')

from vigilo.models.configure import configure_db
configure_db(settings['database'], 'sqlalchemy_')

from vigilo.models.session import metadata, DBSession
from vigilo.models.tables import StateName

from vigilo.correlator.context import Context
from vigilo.correlator.memcached_connection import MemcachedConnection
from vigilo.correlator.db_thread import DummyDatabaseWrapper
from vigilo.correlator.actors.rule_dispatcher import RuleDispatcher
from vigilo.correlator.actors.executor import Executor

from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)

MemcachedConnection.CONTEXT_TIMER = 0
defer.Deferred.debug = 1

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

    # Juste pour être sûr...
    if mc_pid:
        LOGGER.info("Forcefully stopping previous instance of memcached")
        teardown_mc()

    settings['correlator']['memcached_host'] = "127.0.0.1"
    port = get_available_port()
    settings['correlator']['memcached_port'] = port
    env = os.environ.copy()
    env["PATH"] += ":/usr/sbin" # Sur mandriva, memcached est dans /usr/sbin
    memcached_bin = None
    LOGGER.info("Configuring memcached to run on port %d", port)
    mc_pid = subprocess.Popen(["memcached", "-l", "127.0.0.1", "-p", str(port)],
                               env=env, close_fds=True).pid
    # Give it time to start up properly. I should try a client connection in a
    # while loop. Oh well...
    MemcachedConnection.reset()
    time.sleep(1)
    MemcachedConnection()

def teardown_mc():
    """Détruit le serveur memcached créé pour le passage d'un test."""
    global mc_pid
    LOGGER.info("Killing memcached instance running on port %d",
        settings['correlator']['memcached_port'])
    try:
        # Tue le serveur memcached lancé en arrière-plan.
        os.kill(mc_pid, signal.SIGTERM)
        os.wait() # Avoid zombies. Bad zombies.
    except OSError, e:
        # We mostly ignore errors, maybe we should
        # do something more useful here.
        print e
    finally:
        mc_pid = None
    return MemcachedConnection.reset()

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
    DBSession.expunge_all()
    DBSession.rollback()
    DBSession.flush()
    metadata.drop_all()


# Mocks

class ConnectionStub(object):
    # Variable de classe (partagée). Penser à la réinitialiser en tearDown
    data = {}

    def __init__(self, *args, **kwargs):
        self._must_defer = kwargs.pop('must_defer', False)
        super(ConnectionStub, self).__init__(*args, **kwargs)

    def get(self, key, transaction=True):
        # pylint: disable-msg=E0202
        # An attribute inherited from TestApiFunctions hide this method (Mock)
        print "GETTING: %r = %r" % (key, self.data.get(key))
        value = self.data.get(key)
        return self._must_defer and defer.succeed(value) or value

    def set(self, key, value, transaction=True, **kwargs):
        print "SETTING: %r = %r" % (key, value)
        self.data[key] = value
        if self._must_defer:
            return defer.succeed(None)

    def delete(self, key, transaction=True):
        # pylint: disable-msg=E0202
        # An attribute inherited from TestApiFunctions hide this method (Mock)
        print "DELETING: %r = %r" % (key, self.data[key])
        del self.data[key]
        if self._must_defer:
            return defer.succeed(None)

    def topology(self):
        topology = self.get('vigilo:topology')


class ContextStub(Context):
    def __init__(self, msgid, timeout=None, must_defer=True):
        self._connection = ConnectionStub(must_defer=must_defer)
        self._id = str(msgid)
        if timeout is None:
            timeout = 60.0
        self._timeout = timeout
        self._transaction = False
        self._database = DummyDatabaseWrapper(True)


class ContextStubFactory(object):
    def __init__(self):
        self.contexts = {}

    def __call__(self, msgid, database=None, timeout=None, *args, **kwargs):
        if msgid not in self.contexts:
            print "CREATING CONTEXT FOR", msgid
            must_defer = kwargs.pop('must_defer', True)
            self.contexts[msgid] = ContextStub(msgid, timeout, must_defer=must_defer)
        else:
            print "GETTING PREVIOUS CONTEXT FOR", msgid
        return self.contexts[msgid]

    def reset(self):
        # On réinitialise les données de tous les contextes.
        # On ne peut pas écraser le _connection.data de chaque
        # contexte séparément car la modification ne serait vue
        # que pour cette instance du contexte.
        print "CLEARING CONTEXTS"
        ConnectionStub.data = {}



class RuleDispatcherStub(RuleDispatcher):
    """Classe simulant le fonctionnement du RuleDispatcher"""
    def __init__(self):
        database = DummyDatabaseWrapper(True)
        RuleDispatcher.__init__(self, database, "HLS", None, 0, 4, 20)
        self.buffer = []

    def sendItem(self, msg):
        """Simule l'écriture d'un message sur la file"""
        LOGGER.info("Sending this payload to the bus: %r", msg)
        self.buffer.append(msg)

    def clear(self):
        """Vide la file de messages"""
        self.buffer = []

    def registerCallback(self, fn, *args, **kwargs):
        pass

    def doWork(self, f, *args, **kwargs):
        return defer.maybeDeferred(f, *args, **kwargs)



class MemcachedStub(object):
    def _get(self, *a):
        LOGGER.debug("Memcached GET: %r", a)
        # La 2ème valeur correspond à la chaîne  "bar" en pickle.
        return defer.succeed( (1, "S'bar'\np1\n.") )

    def _set(self, *a):
        LOGGER.debug("Memcached SET: %r", a)
        return defer.succeed(True)

    def _delete(self, *a):
        LOGGER.debug("Memcached DELETE: %r", a)
        return defer.succeed(True)

    get = Mock(side_effect=_get)
    set = Mock(side_effect=_set)
    delete = Mock(side_effect=_delete)

    @classmethod
    def getInstance(cls):
        return defer.succeed(cls())


class MemcachedConnectionStub(MemcachedConnection):
    def __new__(cls, *args, **kwargs):
        cls.instance = object.__new__(cls)
        cls.instance._cache = MemcachedStub()
        return cls.instance



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
