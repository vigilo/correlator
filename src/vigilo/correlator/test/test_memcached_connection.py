# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""Suite de tests pour la classe 'MemcachedConnection"""

import unittest

try:
    import cPickle as pickle
except ImportError:
    import pickle

import memcache as mc
from vigilo.correlator.memcached_connection import MemcachedConnection
from utils import setup_mc, teardown_mc
from vigilo.correlator.context import Context

from vigilo.common.conf import settings
    
class TestMemcachedConnection(unittest.TestCase):
    """Test des méthodes de la classe 'MemcachedConnection'"""
        
    def tearDown(self):
        """Arrêt du serveur Memcached à la fin de chaque test."""
        teardown_mc()

    def test_singleton(self):
        """Unicité de la connexion au serveur MemcacheD."""
        
        # On initialise le serveur Memcached.
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

    def test_no_memcache(self):
        """Teste les contextes de corrélation en l'absence de memcached."""
        key = "vigilo_test_no_memcache"
        value = "test_no_memcache"
        
        ctx = Context('test_no_memcache')
        ctx.occurrences_count = 42

        # On tente à nouveau de supprimer la clé 'key'
        self.assertEqual(42, ctx.occurrences_count)

