# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

""" Connexion au serveur MemcacheD. """

try:
    import cPickle as pickle
except ImportError:
    import pickle

import transaction
from datetime import datetime
import time
from twisted.internet import task, defer, reactor, protocol
from twisted.python.failure import Failure
from twisted.protocols.memcache import MemCacheProtocol

from sqlalchemy.exc import OperationalError

from vigilo.common.conf import settings
from vigilo.common.logging import get_logger
from vigilo.common.gettext import translate

LOGGER = get_logger(__name__)
_ = translate(__name__)

__all__ = (
    'MemcachedConnection',
)

class VigiloMemCacheProtocol(MemCacheProtocol):
    def connectionMade(self):
        """
        Appelle la méthode C{connectionMade} de la factory
        lorsque la connexion à memcached est établie.
        """
        if hasattr(self.factory, 'clientConnectionMade'):
            self.factory.clientConnectionMade(self)

class MemcachedClientFactory(protocol.ReconnectingClientFactory):
    """
    Factory pour le protocole memcached supportant les reconnexions
    automatiques.
    """
    maxDelay = 10
    _waiting = []
    _instance = None

    # Évite que le délai maximum de reconnexion soit atteint
    # trop rapidement (ce qui arrive avec la valeur par défaut).
    factor = 1.6180339887498948

    def clientConnectionMade(self, protocol):
        """
        Méthode appelée lorsque le protocole sous-jacent est prêt.
        Cette méthode déclenche l'exécution des C{Deferred} qui
        dépendent du protocole.

        @type: Instance (initialisée) du protocole.
        @rtype: L{VigiloMemCacheProtocol}
        """
        self.resetDelay()
        LOGGER.info(_("Connected to memcached (%s)"),
            protocol.transport.getPeer())
        self._instance = protocol
        for d in self._waiting:
            try:
                d.callback(protocol)
            except defer.AlreadyCalledError:
                # @FIXME: est-ce qu'on devrait vraiment ignorer l'erreur ?
                # Pour le moment je n'ai eu cette erreur que dans les tests.
                pass
        self._waiting = []

    def startedConnecting(self, connector):
        """
        Méthode appelée lorsque la connexion au serveur memcached
        est en cours.
        """
        LOGGER.info(_("Connecting to memcached server (%s)..."),
                    connector.getDestination())
        return protocol.ReconnectingClientFactory.startedConnecting(
            self, connector)

    def clientConnectionLost(self, connector, reason):
        """
        Méthode appelée lorsque la connexion à memcached est perdue.
        """
        LOGGER.info(_("Connection to memcached (%(conn)s) lost: %(reason)s"), {
                        'conn': connector.getDestination(),
                        'reason': reason,
                    })
        self._instance = None
        return protocol.ReconnectingClientFactory.clientConnectionLost(
            self, connector, reason)

    def clientConnectionFailed(self, connector, reason):
        """
        Méthode appelée lorsque la connexion à memcached n'a pas pu
        être établie.
        """
        LOGGER.info(_("Connection to memcached (%(conn)s) failed: %(reason)s"), {
                        'conn': connector.getDestination(),
                        'reason': reason,
                    })
        self._instance = None
        return protocol.ReconnectingClientFactory.clientConnectionFailed(
            self, connector, reason)

    def getInstance(self):
        """
        Retourne un C{Deferred} qui permettra d'interagir avec le cache.

        @return: Instance permettant d'interagir avec le cache.
        @rtype: L{VigiloMemCacheProtocol}
        """
        if self._instance is not None:
            return defer.succeed(self._instance)
        d = defer.Deferred()
        self._waiting.append(d)
        return d

    def reset(self):
        self.stopTrying()
        # Nécessaire car stopTrying empêche la (re)connexion,
        # mais n'interrompt pas les connexions actives.
        if self.connector:
            self.connector.disconnect()

        self.stopFactory()

        # On arrête l'éventuel IDelayedCall généré
        # lors d'une reconnexion.
        if self._callID:
            try:
                self._callID.cancel()
            except KeyboardInterrupt:
                raise
            except:
                pass

        self._instance = None
        self._waiting = []

class MemcachedConnection(object):
    """
    Classe gérant la connexion et les échanges avec
    le serveur MemcacheD.
    """
     # Attribut statique de classe
    instance = None

    # Maximum de secondes au-delà duquel memcached
    # considère que l'expiration est une date absolue
    # dans le temps (timestamp Unix) et non relative.
    MAX_RELATIVE = 60 * 60 * 24 * 30

    def __new__(cls, *args, **kwargs):
        """
        Constructeur

        @TODO: améliorer la doc ici : cherche-t-on à faire un singleton ?
        @return: Une instance de la classe L{cls}.
        @rtype: L{cls}
        """
        if cls.instance is None:
            # Construction de l'objet..
            cls.instance = object.__new__(cls)

            # Connexion à memcached en utilisant la factory
            # qui se reconnecte automatiquement.
            mc_host = settings['correlator']['memcached_host']
            mc_port = settings['correlator'].as_int('memcached_port')
            factory = MemcachedClientFactory()
            factory.protocol = lambda: VigiloMemCacheProtocol(timeOut=2)
            connector = reactor.connectTCP(mc_host, mc_port, factory)
            cls.instance._connector = connector
            cls.instance._cache = connector.factory
        return cls.instance

    def __init__(self):
        """
        Initialisation de la connexion.
        """
        # Si vous devez initialiser des attributs, faîtes le dans __new__
        # et non dans __init__ : __new__ ne fera l'initialisation qu'une
        # fois (singleton). Dans __init__, l'attribut serait réinitialisé
        # à chaque récupération d'une instance.
        pass

    def __convert_to_datetime(self, timestamp):
        if not timestamp:
            return None
        if timestamp > self.MAX_RELATIVE:
            return datetime.fromtimestamp(timestamp)
        return datetime.fromtimestamp(timestamp + time.time())

    @classmethod
    def reset(cls):
        """
        Permet de supprimer le singleton qui gère la connexion
        à memcached.

        @note: En temps normal, vous NE DEVEZ PAS utiliser cette méthode.
            Cette méthode n'existe que pour faciliter le travail des
            tests unitaires de cette classe.
        """
        if cls.instance is None:
            return
        if cls.instance._connector:
            cls.instance._connector.disconnect()
        if cls.instance._cache:
            cls.instance._cache.reset()
        del cls.instance
        cls.instance = None

    def set(self, key, value, transaction=True, **kwargs):
        """
        Associe la valeur 'value' à la clé 'key'.

        @param key: La clé à laquelle associer la valeur.
        @type key: C{str}
        @param value: La valeur à enregistrer.
        @type value: C{str}

        @return: Un entier non nul si l'enregistrement a réussi.
        @rtype: C{int}
        """
        LOGGER.debug(_("Trying to set value '%(value)s' for key '%(key)s' "
                        "(transaction=%(txn)r)."), {
                        'key': key,
                        'value': value,
                        'txn': transaction,
                    })

        # On sérialise la valeur avant son enregistrement
        pick_value = pickle.dumps(value)
        exp_time = self.__convert_to_datetime(kwargs.pop('time', None))
        flags = kwargs.pop('flags', 0)

        # memcached utilise 0 pour indiquer l'absence d'expiration.
        if exp_time is None:
            exp_time = 0
        else:
            exp_time = int(time.mktime(exp_time.timetuple()))

        def _check_set(res):
            # Lève une exception si la valeur n'a pas pu être stockée.
            if not res:
                raise Exception

        d = self._cache.getInstance()
        d.addCallback(lambda cache: cache.set(key, pick_value, flags, exp_time))
        d.addCallback(_check_set)
        return d

    def get(self, key, transaction=True, flags=0):
        """
        Récupère la valeur associée à la clé 'key'.
        Renvoie None si cette clé n'existe pas.

        @param key: La clé dans laquelle enregistrer la valeur.
        @type key: C{str}

        @return: La valeur associée à la clé 'key', ou None.
        @rtype: C{str} || None
        """

        LOGGER.debug(_("Trying to get the value of the key '%(key)s'"
                        " (transaction=%(txn)r)."), {
                            'key': key,
                            'txn': transaction,
                        })

        def _check_result(result, key, txn, flags):
            # Idéalement, on voudrait pouvoir traiter ce cas différemment,
            # mais le rule_dispatcher ne définit pas forcément à l'avance
            # tous les attributs du contexte qu'il est susceptible d'utiliser.
            if result[-1] is None:
                return None
            return pickle.loads(str(result[-1]))

        d = self._cache.getInstance()
        d.addCallback(lambda cache: cache.get(key))
        d.addCallback(_check_result, key, transaction, flags)
        return d

    def delete(self, key, transaction=True):
        """
        Supprime la clé 'key' et la valeur qui lui est associée.

        @param key: La clé à supprimer.
        @type key: C{str}

        @return: Un entier non nul si la suppression a réussi.
        @rtype: C{int}
        """

        LOGGER.debug(_("Trying to delete the key '%(key)s' "
                        "(transaction=%(txn)r)."), {
                            'key': key,
                            'txn': transaction,
                        })

        d = self._cache.getInstance()
        d.addCallback(lambda cache: cache.delete(key))
        return d

