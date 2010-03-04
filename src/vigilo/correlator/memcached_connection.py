# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
""" Connexion au serveur MemcacheD. """

try:
    import cPickle as pickle
except ImportError:
    import pickle

import memcache as mc
        
from vigilo.common.conf import settings

from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)
from vigilo.common.gettext import translate
_ = translate(__name__)

class MemcachedConnectionError(Exception): 
    """Exception levée lorsque le serveur MemcacheD est inaccessible."""
    pass 

class MemcachedConnection():
    """
    Classe gérant la connexion et les échanges avec
    le serveur MemcacheD. Hérite de la classe mc.
    """
    
    def __init__(self):
        """
        Initialisation de la connexion.
        """
        
        # Initialisation de l'attribut contenant la connexion.
        self.__connection = None
    
    def __connect(self):
        """
        Établit la connexion.
        """
        
        # Si la connexion n'est pas déjà établie
        if not self.is_connection_established():
            
            # Clôture d'une éventuelle connection ouverte
            # précédemment et devenue inopérante.
            if self.__connection:
                self.__connection.disconnect_all()
        
            # Récupération des informations de connection.
            host = settings['correlator']['memcached_host']
            port = settings['correlator'].as_int('memcached_port')
            conn_str = '%s:%d' % (host, port)
    
            # Établissement de la connexion.
            LOGGER.info(_("Establishing connection to memcached server..."))
            self.__connection = mc.Client([conn_str])
            self.__connection.behaviors = {'support_cas': 1}
            
            # Si la connexion n'a pas pu être établie
            if not self.is_connection_established():
                # On lève une exception
                LOGGER.critical(_("Could not connect to memcached server, "
                                  "make sure it is running"))
                raise MemcachedConnectionError
    
    def is_connection_established(self):
        """
        Vérifie que la connexion est bien établie.
        
        @return: True si la connexion est bien établie, False le cas échéant.
        @rtype: C{bool}
        """
        
        if not self.__connection or not self.__connection.set('vigilo', 1):
            return False
        return True
    
    def set(self, key, value):
        """
        Associe la valeur 'value' à la clé 'key'.
        
        @param key: La clé à laquelle associer la valeur.
        @type key: C{str}
        @param value: La valeur à enregistrer.
        @type value: C{str}
        
        @return: Un entier non nul si l'enregistrement a réussi.
        @rtype: C{int}
        """
        
        # On établit la connection au serveur
        # Memcached si elle n'est pas déjà opérante.
        self.__connect()
        
        # On sérialise la valeur 'value' avant son enregistrement
        value = pickle.dumps(value)
        
        # On associe la valeur 'value' à la clé 'key'.
        return self.__connection.set(key, value)
    
    def get(self, key):
        """
        Récupère la valeur associée à la clé 'key'.
        Renvoie None si cette clé n'existe pas.
        
        @param key: La clé dans laquelle enregistrer la valeur.
        @type key: C{str}
        
        @return: La valeur associée à la clé 'key', ou None.
        @rtype: C{str} || None
        """
        
        # On établit la connection au serveur
        # Memcached si elle n'est pas déjà opérante.
        self.__connect()
        
        # On récupère la valeur associée à la clé 'key'.
        result = self.__connection.get(key)
        
        # On "dé-sérialise" la valeur avant de la retourner
        if not result:
            return None
        return pickle.loads(result)
    
    def delete(self, key):
        """
        Supprime la clé 'key' et la valeur qui lui est associée.
        
        @param key: La clé à supprimer.
        @type key: C{str}
        
        @return: Un entier non nul si la suppression a réussi.
        @rtype: C{int}
        """
        
        # On établit la connection au serveur
        # Memcached si elle n'est pas déjà opérante.
        self.__connect()
        
        # On supprime la clé 'key' et la valeur qui lui est associée.
        return self.__connection.delete(key)

