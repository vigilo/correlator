# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# pylint: disable-msg=C0111,W0212,R0904
# Copyright (C) 2006-2016 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""Suite de tests pour la classe 'MemcachedConnection"""

import unittest

from nose.twistedtools import reactor  # pylint: disable-msg=W0611
from nose.twistedtools import deferred

from twisted.internet import defer, protocol, error
from twisted.protocols.memcache import MemCacheProtocol

try:
    import cPickle as pickle
except ImportError:
    import pickle

from vigilo.correlator.test import helpers
from vigilo.correlator.memcached_connection import MemcachedConnection

from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)

class TestMemcachedConnection(unittest.TestCase):
    """
    Test des méthodes de la classe 'MemcachedConnection'

    Le setUp et le tearDown sont décorés par @deferred() pour que la création
    de la base soit réalisée dans le même threads que les accès dans les tests.
    """

    @deferred(timeout=60)
    def setUp(self):
        super(TestMemcachedConnection, self).setUp()
        helpers.setup_db()
        helpers.setup_mc()
        self.cache = MemcachedConnection()
        return defer.succeed(None)

    @deferred(timeout=60)
    def tearDown(self):
        """Arrêt du serveur Memcached à la fin de chaque test."""
        super(TestMemcachedConnection, self).tearDown()
        self.cache = None
        helpers.teardown_mc()
        helpers.teardown_db()
        return defer.succeed(None)

    @deferred(timeout=10)
    def test_singleton(self):
        """Unicité de la connexion au serveur MemcacheD."""
        # On instancie une 2ème fois la classe MemcachedConnection.
        conn = MemcachedConnection()

        # On s'assure que les deux instances
        # représentent en fait le même objet.
        self.assertEqual(conn, self.cache)
        return defer.succeed(None)

    def _connect(self):
        host = helpers.settings['correlator']['memcached_host']
        port = helpers.settings['correlator'].as_int('memcached_port')
        d_connection = protocol.ClientCreator(
                reactor, MemCacheProtocol
            ).connectTCP(host, port)
        return d_connection

    @deferred(timeout=60)
    @defer.inlineCallbacks
    def test_set(self):
        """Association d'une valeur à une clé"""
        # On initialise le nom de la clé et de la valeur associée
        key = "vigilo_test_set"
        value = "test_set"

        set_value = yield self.cache.set(key, value)
        LOGGER.info("'%s' set to '%s'", key, set_value)

        # On vérifie que la clé a bien été ajoutée
        # et qu'elle est bien associée à la valeur 'value'.
        connection = yield self._connect()
        LOGGER.info("Connected using %r", connection)
        received = yield connection.get(key)
        LOGGER.info("Received: %r", received)
        self.assertEqual(pickle.loads(received[-1]), value)

    @deferred(timeout=60)
    @defer.inlineCallbacks
    def test_get(self):
        """Récupération de la valeur associée à une clé"""

        # On initialise le nom de la clé et de la valeur associée
        key = "vigilo_test_get"
        value = "test_get"

        # On associe la valeur 'value' à la clé 'key'.
        connection = yield self._connect()
        LOGGER.info("Connected using %r", connection)
        res = yield connection.set(key, pickle.dumps(value))
        LOGGER.info("Success? %r", res)

        # On tente à nouveau de récupérer la valeur associée à la clé 'key'
        result = yield self.cache.get(key)

        # On vérifie que la méthode get retourne bien 'value'.
        self.assertEqual(result, value)

    @deferred(timeout=60)
    @defer.inlineCallbacks
    def test_delete(self):
        """Suppression d'une clé"""

        # On initialise le nom de la clé et de la valeur associée
        key = "vigilo_test_delete"
        value = "test_delete"

        # On ajoute la clé 'key'.
        connection = yield self._connect()
        LOGGER.info("Connected using %r", connection)
        yield connection.set(key, value)

        # On tente à nouveau de supprimer la clé 'key'
        yield self.cache.delete(key)

        # On s'assure que la clé a bien été supprimée
        value = yield connection.get(key)
        self.assertEqual(None, value[-1])

    @deferred(timeout=60)
    @defer.inlineCallbacks
    def test_key_spaces(self):
        """Gestion des espaces dans une clé"""
        # On initialise le nom de la clé et de la valeur associée
        key = "vigilo test espace"
        value = "test_espace"

        set_value = yield self.cache.set(key, value)
        LOGGER.info("'%s' set to '%s'", key, set_value)
        get_value = yield self.cache.get(key, value)
        LOGGER.info("'%s' value is '%s'", key, get_value)
        yield self.cache.delete(key)
        LOGGER.info("'%s' deleted", key)

    @deferred(timeout=60)
    @defer.inlineCallbacks
    def test_reconnection(self):
        """Reconnexion automatique à memcached"""
        yield self.cache.set("test", 42)

        # On coupe la connexion. Comme la factory n'a pas demandé
        # cette coupure, elle va automatiquement tenter une reconnexion.
        self.cache._cache._instance.transport.loseConnection()

        # Ce deferred va émettre une exception car la connexion
        # a été perdue entre temps et car le deferred avait été
        # créé AVANT que la perte de connexion ne soit détectée.
        # Avant Twisted 9.0, l'exception est une defer.TimoutError,
        # ensuite il s'agit d'une error.ConnectionDone
        try:
            yield self.cache.get("test")
            self.fail("A TimeoutError exception was expected, got nothing.")
        except (defer.TimeoutError, error.ConnectionDone, KeyboardInterrupt):
            pass
        except Exception as e:
            self.fail("A TimeoutError exception was expected, got %r" % e)

        # Ce get() fonctionnera car la connexion a été rétablie
        # entre temps (reconnexion automatique).
        value = yield self.cache.get("test")
        self.assertEqual(42, value)
