# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# pylint: disable-msg=C0111,W0212,R0904
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""Suite de tests pour la classe 'MemcachedConnection"""

import unittest
from nose.twistedtools import reactor, deferred
from twisted.internet import defer, reactor, protocol
from twisted.protocols.memcache import MemCacheProtocol

try:
    import cPickle as pickle
except ImportError:
    import pickle

from helpers import settings
from helpers import setup_mc, teardown_mc
from helpers import setup_db, teardown_db
from vigilo.correlator.memcached_connection import MemcachedConnection
from vigilo.correlator.context import Context
from vigilo.correlator.db_thread import DummyDatabaseWrapper

class TestMemcachedConnection(unittest.TestCase):
    """Test des méthodes de la classe 'MemcachedConnection'"""

    @deferred(timeout=30)
    def setUp(self):
        super(TestMemcachedConnection, self).setUp()
        setup_db()
        return defer.succeed(None)

    @deferred(timeout=30)
    def tearDown(self):
        """Arrêt du serveur Memcached à la fin de chaque test."""
        super(TestMemcachedConnection, self).tearDown()
        teardown_mc()
        teardown_db()
        return defer.succeed(None)

    @deferred(timeout=30)
    def test_singleton(self):
        """Unicité de la connexion au serveur MemcacheD."""
        setup_mc()

        # On instancie deux fois la classe MemcachedConnection.
        conn1 = MemcachedConnection(DummyDatabaseWrapper(True))
        conn2 = MemcachedConnection(DummyDatabaseWrapper(True))

        # On s'assure que les deux instances
        # représentent en fait le même objet.
        self.assertEqual(conn1, conn2)
        return defer.succeed(None)

    @deferred(timeout=30)
    @defer.inlineCallbacks
    def test_set(self):
        """Association d'une valeur à une clé"""
        # On initialise le nom de la clé et de la valeur associée
        key = "vigilo_test_set"
        value = "test_set"

        # On instancie la classe MemcachedConnection.
        conn = MemcachedConnection(DummyDatabaseWrapper(True))

        # On initialise le serveur Memcached.
        setup_mc()

        # On tente à nouveau d'associer la valeur 'value' à la clé 'key'
        set_value = yield conn.set(key, value)
        print "'%s' set to '%s'" % (key, set_value)

        # On vérifie que la clé a bien été ajoutée
        # et qu'elle est bien associée à la valeur 'value'.
        host = settings['correlator']['memcached_host']
        port = settings['correlator'].as_int('memcached_port')
        connection = yield protocol.ClientCreator(
                reactor, MemCacheProtocol
            ).connectTCP(host, port)
        print "Connected to %s:%d using %r" % (host, port, connection)
        received = yield connection.get(key)
        print "Received: %r" % (received, )
        self.assertEqual(pickle.loads(received[-1]), value)

    @deferred(timeout=30)
    @defer.inlineCallbacks
    def test_get(self):
        """Récupération de la valeur associée à une clé"""

        # On initialise le nom de la clé et de la valeur associée
        key = "vigilo_test_get"
        value = "test_get"

        # On instancie la classe MemcachedConnection.
        conn = MemcachedConnection(DummyDatabaseWrapper(True))

        # On initialise le serveur Memcached.
        setup_mc()

        # On associe la valeur 'value' à la clé 'key'.
        host = settings['correlator']['memcached_host']
        port = settings['correlator'].as_int('memcached_port')
        connection = yield protocol.ClientCreator(
                reactor, MemCacheProtocol
            ).connectTCP(host, port)
        print "Connecting to %s:%d using %r" % (host, port, connection)
        res = yield connection.set(key, pickle.dumps(value))
        print "Success?", res

        # On tente à nouveau de récupérer la valeur associée à la clé 'key'
        result = yield conn.get(key)

        # On vérifie que la méthode get retourne bien 'value'.
        self.assertEqual(result, value)

    @deferred(timeout=30)
    @defer.inlineCallbacks
    def test_delete(self):
        """Suppression d'une clé"""

        # On initialise le nom de la clé et de la valeur associée
        key = "vigilo_test_delete"
        value = "test_delete"

        # On instancie la classe MemcachedConnection.
        conn = MemcachedConnection(DummyDatabaseWrapper(True))

        # On initialise le serveur Memcached.
        setup_mc()

        # On ajoute la clé 'key'.
        host = settings['correlator']['memcached_host']
        port = settings['correlator'].as_int('memcached_port')
        print "Connecting to %s:%d" % (host, port)
        connection = yield protocol.ClientCreator(
                reactor, MemCacheProtocol
            ).connectTCP(host, port)
        yield conn.set(key, value)

        # On tente à nouveau de supprimer la clé 'key'
        yield conn.delete(key)

        # On s'assure que la clé a bien été supprimée
        value = yield connection.get(key)
        self.assertEquals(None, value[-1])


class TestMemcachedWithoutAnyConnection(unittest.TestCase):
    """
    Le setUp et le tearDown sont décorés par @deferred() pour que la création
    de la base soit réalisée dans le même threads que les accès dans les tests.
    """

    @deferred(timeout=30)
    def setUp(self):
        setup_db()
        return defer.succeed(None)

    @deferred(timeout=30)
    def tearDown(self):
        super(TestMemcachedWithoutAnyConnection, self).tearDown()
        teardown_db()
        return defer.succeed(None)

    @deferred(timeout=30)
    @defer.inlineCallbacks
    def test_no_memcache(self):
        """Teste les contextes de corrélation en l'absence de memcached."""
        key = "vigilo_test_no_memcache"
        value = "test_no_memcache"

        ctx = Context('test_no_memcache', database=DummyDatabaseWrapper(True))
        yield ctx.set('occurrences_count', 42)

        # On tente à nouveau de supprimer la clé 'key'
        occurrences_count = yield ctx.get('occurrences_count')
        self.assertEqual(42, occurrences_count)
