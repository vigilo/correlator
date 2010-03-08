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

class MemcachedConnection(object):
    """
    Classe gérant la connexion et les échanges avec
    le serveur MemcacheD. Hérite de la classe mc.
    """
    
     # Attribut statique de classe
    instance = None
    
    def __new__(cls):
        """
        Constructeur
        
        @return: Une instance de la classe L{cls}.
        @rtype: L{cls}
        """
        if cls.instance is None:
            # Construction de l'objet..
            cls.instance = object.__new__(cls)
            # Initialisation de l'attribut contenant la connexion.
            cls.instance.__connection = None
        return cls.instance
    
    def __init__(self):
        """
        Initialisation de la connexion.
        """
    
    def connect(self):
        """
        Établit la connexion.
        """

        # Clôture d'une éventuelle connection ouverte
        # précédemment et devenue inopérante.
        if self.__connection:
            # Si la connexion est en fait encore active on ne fait rien.
            if self.__connection.set('vigilo', 1):
                return
            self.__connection.disconnect_all()
    
        # Récupération des informations de connection.
        host = settings['correlator']['memcached_host']
        port = settings['correlator'].as_int('memcached_port')
        conn_str = '%s:%d' % (host, port)

        # Établissement de la connexion.
        LOGGER.info(_("Establishing connection to MemcacheD"
                      " server (%s)...") % (conn_str, ))
        self.__connection = mc.Client([conn_str])
        self.__connection.behaviors = {'support_cas': 1}
    
    def set(self, key, value, *args, **kwargs):
        """
        Associe la valeur 'value' à la clé 'key'.
        
        @param key: La clé à laquelle associer la valeur.
        @type key: C{str}
        @param value: La valeur à enregistrer.
        @type value: C{str}
        
        @raise MemcachedConnectionError: Exception levée
        lorsque la connexion au serveur MemcacheD est inopérante.
        
        @return: Un entier non nul si l'enregistrement a réussi.
        @rtype: C{int}
        """
        
        # On établit la connection au serveur Memcached si nécessaire.
        if not self.__connection:
            self.connect()
        
        # On sérialise la valeur 'value' avant son enregistrement
        value = pickle.dumps(value)
        
        # On associe la valeur 'value' à la clé 'key'.
        result = self.__connection.set(key, value, *args, **kwargs)
        
        # Si l'enregistrement a échoué on doit
        # s'assurer que la connexion est bien opérante :
        if not result:
            
            # On tente de rétablir la connection au serveur MemcacheD.
            self.connect()
            
            # On essaye une nouvelle fois d'associer
            # la valeur 'value' à la clé 'key'.
            result = self.__connection.set(key, value)
        
            # Si l'enregistrement a de nouveau échoué
            if not result:
                # On lève une exception
                LOGGER.critical(_("Could not connect to memcached server, "
                                  "make sure it is running"))
                raise MemcachedConnectionError
            
        return result
            
    
    def get(self, key):
        """
        Récupère la valeur associée à la clé 'key'.
        Renvoie None si cette clé n'existe pas.
        
        @param key: La clé dans laquelle enregistrer la valeur.
        @type key: C{str}
        
        @raise MemcachedConnectionError: Exception levée
        lorsque la connexion au serveur MemcacheD est inopérante.
        
        @return: La valeur associée à la clé 'key', ou None.
        @rtype: C{str} || None
        """
        
        # On établit la connection au serveur Memcached si nécessaire.
        if not self.__connection:
            self.connect()
        
        # On récupère la valeur associée à la clé 'key'.
        result = self.__connection.get(key)

        # Si l'opération a échoué on doit s'assurer
        # que la connexion est bien opérante :
        if not result:
            
            # On tente de rétablir la connection au serveur MemcacheD.
            self.connect()
            
            # On essaye une nouvelle fois de récupèrer
            # la valeur associée à la clé 'key'.
            result = self.__connection.get(key)
        
            # Si l'opération a de nouveau échoué
            if not result:
                # On fait ici la distinction entre le cas de
                # l'erreur de connexion et celui de la clé
                # manquante, distinction que MemcacheD ne fait pas.
                if self.__connection.set('vigilo', 1):
                    return None

                # On lève une exception
                LOGGER.critical(_("Could not connect to memcached server, "
                                  "make sure it is running"))
                raise MemcachedConnectionError
        
        # On "dé-sérialise" la valeur avant de la retourner
        return pickle.loads(result)
    
    def delete(self, key):
        """
        Supprime la clé 'key' et la valeur qui lui est associée.
        
        @param key: La clé à supprimer.
        @type key: C{str}
        
        @raise MemcachedConnectionError: Exception levée
        lorsque la connexion au serveur MemcacheD est inopérante.
        
        @return: Un entier non nul si la suppression a réussi.
        @rtype: C{int}
        """
        
        # On établit la connection au serveur Memcached si nécessaire.
        if not self.__connection:
            self.connect()
        
        # On supprime la clé 'key' et la valeur qui lui est associée.
        result = self.__connection.delete(key)
        
        # Si la suppression a échoué on doit s'assurer
        # que la connexion est bien opérante :
        if not result:
            
            # On tente de rétablir la connection au serveur MemcacheD.
            self.connect()
            
            # On essaye une nouvelle fois de supprimer la clé 'key'.
            result = self.__connection.delete(key)
        
            # Si la suppression a de nouveau échoué
            if not result:
                # On lève une exception
                LOGGER.critical(_("Could not connect to memcached server, "
                                  "make sure it is running"))
                raise MemcachedConnectionError
            
        return result

