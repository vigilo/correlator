# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# pylint: disable-msg=C0111,W0212,R0904
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""Suite de tests pour la classe 'MemcachedConnection"""

# ATTENTION: ne pas utiliser twisted.trial, car nose va ignorer les erreurs
# produites par ce module !!!
from nose.twistedtools import reactor, deferred
from twisted.internet import defer

import unittest

try:
    import cPickle as pickle
except ImportError:
    import pickle

import memcache as mc
from utils import settings
from utils import setup_mc, teardown_mc
from utils import setup_db, teardown_db
from vigilo.correlator.memcached_connection import MemcachedConnection
from vigilo.correlator.context import Context

class TestMemcachedConnection(unittest.TestCase):
    """Test des méthodes de la classe 'MemcachedConnection'"""

    def setUp(self):
        super(TestMemcachedConnection, self).setUp()
        setup_db()

    def tearDown(self):
        """Arrêt du serveur Memcached à la fin de chaque test."""
        super(TestMemcachedConnection, self).tearDown()
        teardown_mc()
        teardown_db()

    def test_singleton(self):
        """Unicité de la connexion au serveur MemcacheD."""
        setup_mc()

        # On instancie deux fois la classe MemcachedConnection.
        conn1 = MemcachedConnection()
        conn2 = MemcachedConnection()

        # On s'assure que les deux instances
        # représentent en fait le même objet.
        self.assertEqual(conn1, conn2)


    def test_set(self):
        """Association d'une valeur à une clé"""
        # On initialise le nom de la clé et de la valeur associée
        key = "vigilo_test_set"
        value = "test_set"

        # On instancie la classe MemcachedConnection.
        conn = MemcachedConnection()

        # On initialise le serveur Memcached.
        setup_mc()

        # On tente à nouveau d'associer la valeur 'value' à la clé 'key'
        conn.set(key, value)

        # On vérifie que la clé a bien été ajoutée
        # et qu'elle est bien associée à la valeur 'value'.
        host = settings['correlator']['memcached_host']
        port = settings['correlator'].as_int('memcached_port')
        conn_str = '%s:%d' % (host, port)
        connection = mc.Client([conn_str])
        connection.behaviors = {'support_cas': 1}
        self.assertEqual(pickle.loads(connection.get(key)), value)

    def test_get(self):
        """Récupération de la valeur associée à une clé"""

        # On initialise le nom de la clé et de la valeur associée
        key = "vigilo_test_get"
        value = "test_get"

        # On instancie la classe MemcachedConnection.
        conn = MemcachedConnection()

        # On initialise le serveur Memcached.
        setup_mc()

        # On associe la valeur 'value' à la clé 'key'.
        host = settings['correlator']['memcached_host']
        port = settings['correlator'].as_int('memcached_port')
        conn_str = '%s:%d' % (host, port)
        connection = mc.Client([conn_str])
        connection.behaviors = {'support_cas': 1}
        connection.set(key, pickle.dumps(value))

        # On tente à nouveau de récupérer la valeur associée à la clé 'key'
        result = conn.get(key)

        # On vérifie que la méthode get retourne bien 'value'.
        self.assertEqual(result, value)

    def test_delete(self):
        """Suppression d'une clé"""

        # On initialise le nom de la clé et de la valeur associée
        key = "vigilo_test_delete"
        value = "test_delete"

        # On instancie la classe MemcachedConnection.
        conn = MemcachedConnection()

        # On initialise le serveur Memcached.
        setup_mc()

        # On ajoute la clé 'key'.
        host = settings['correlator']['memcached_host']
        port = settings['correlator'].as_int('memcached_port')
        conn_str = '%s:%d' % (host, port)
        connection = mc.Client([conn_str])
        connection.behaviors = {'support_cas': 1}
        conn.set(key, value)

        # On tente à nouveau de supprimer la clé 'key'
        self.assertTrue(conn.delete(key))

        # On s'assure que la clé a bien été supprimée
        self.assertFalse(connection.get(key))

class TestMemcachedWithoutAnyConnection(unittest.TestCase):
    def tearDown(self):
        super(TestMemcachedWithoutAnyConnection, self).tearDown()
        teardown_db()

    @deferred(timeout=30)
    @defer.inlineCallbacks
    def test_no_memcache(self):
        """Teste les contextes de corrélation en l'absence de memcached."""
        setup_db()

        key = "vigilo_test_no_memcache"
        value = "test_no_memcache"

        ctx = Context('test_no_memcache')
        yield ctx.set('occurrences_count', 42)

        # On tente à nouveau de supprimer la clé 'key'
        occurrences_count = yield ctx.get('occurrences_count')
        self.assertEqual(42, occurrences_count)
