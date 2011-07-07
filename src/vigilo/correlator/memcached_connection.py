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

from vigilo.models.tables import CorrelationContext
from vigilo.models.session import DBSession

LOGGER = get_logger(__name__)
_ = translate(__name__)

__all__ = (
    'MemcachedConnection',
)

class ReconnectingMemcachedClientFactory(protocol.ReconnectingClientFactory):
    maxDelay = 60

    def buildProtocol(self, addr):
        self.resetDelay()
        return MemCacheProtocol(10)

class MemcachedConnection(object):
    """
    Classe gérant la connexion et les échanges avec
    le serveur MemcacheD.
    """
     # Attribut statique de classe
    instance = None

    use_database = True

    # Maximum de secondes au-delà duquel memcached
    # considère que l'expiration est une date absolue
    # dans le temps (timestamp Unix) et non relative.
    MAX_RELATIVE = 60 * 60 * 24 * 30

    CONTEXT_TIMER = 60.

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
            cls.instance.__connection_cache = None
            cls.instance.__connection_cache_deferred = None
            cls.instance.__connection_db_session = None
            cls.instance.__expiration = task.LoopingCall(
                cls.instance.__remove_expired_contexts)

            # Le timer est réglé sur 0 dans les tests unitaires,
            # où nous n'avons pas besoin d'expirer les contextes.
            if cls.CONTEXT_TIMER:
                cls.instance.__expiration_defer = \
                    cls.instance.__expiration.start(cls.CONTEXT_TIMER)

        return cls.instance

    def __init__(self, database):
        """
        Initialisation de la connexion.
        """
        # Si vous devez initialiser des attributs, faîtes le dans __new__
        # et non dans __init__ : __new__ ne fera l'initialisation qu'une
        # fois (singleton). Dans __init__, l'attribut serait réinitialisé
        # à chaque récupération d'une instance.
        self.__connection_db_session = database

    def __del__(self):
        """
        Destruction de la connexion à memcached.
        """
        self.__expiration.stop()
        self.__expiration_defer.cancel()

    def __convert_to_datetime(self, timestamp):
        if not timestamp:
            return None
        if timestamp > self.MAX_RELATIVE:
            return datetime.fromtimestamp(timestamp)
        return datetime.fromtimestamp(timestamp + time.time())

    def __remove_expired_contexts(self):
        if self.__connection_db_session is None or not self.use_database:
            return
        now = datetime.now()
        d = self.__connection_db_session.run(
            DBSession.query(
                    CorrelationContext
            ).filter(CorrelationContext.expiration_date < now
            ).delete,
        )

        def print_stats(nb_deleted):
            LOGGER.debug(_(
                'Deleted %(nb_deleted)d expired '
                'correlation contexts'), {
                    'nb_deleted': nb_deleted,
                })

        d.addCallback(print_stats)
        return d

    @classmethod
    def reset(cls):
        """
        Permet de supprimer le singleton qui gère la connexion
        à memcached.

        @note: En temps normal, vous NE DEVEZ PAS utiliser cette méthode.
            Cette méthode n'existe que pour faciliter le travail des
            tests unitaires de cette classe.
        """
        del cls.instance
        cls.instance = None

    def __get_connection(self):
        if self.__connection_cache_deferred:
            return self.__connection_cache_deferred

        mc_host = settings['correlator']['memcached_host']
        mc_port = settings['correlator'].as_int('memcached_port')
        LOGGER.info(_("Establishing connection to MemcacheD "
                        "server (%s)..."), "%s:%d" % (mc_host, mc_port))

        d = protocol.ClientCreator(
                reactor,
                MemCacheProtocol,
                # Délai de détection de perte de connexion à memcached.
                1,
            ).connectTCP(mc_host, mc_port, timeout=2)

        def eb(failure):
            LOGGER.info(
                _("Could not connect to memcached: %s"),
                str(failure).decode('utf-8')
            )
            self.__connection_cache_deferred = None
            return None

        def cb(proto):
            # La connexion précédente a fait un timeout,
            # on vide le cache histoire d'éviter de récupérer
            # des données obsolètes.
            if self.__connection_cache and proto:
                proto = proto.flushAll()
                proto.addErrback(self._eb)
            self.__connection_cache = proto

        d.addErrback(eb)
        d.addCallback(cb)
        self.__connection_cache_deferred = d
        return d

    def _eb(self, failure):
        LOGGER.info(
            _("Lost connection to memcached: %s"),
            str(failure).decode('utf-8')
        )
        self.__connection_cache_deferred = None
        return self.__get_connection()

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

        def set_db(exp_time):
            if self.use_database:
                instance = CorrelationContext(key=key)
                instance = DBSession.merge(instance)
                instance.value = pick_value
                instance.expiration_date = exp_time
                DBSession.add(instance)
                DBSession.flush()

        def prep_exp_time(res, exp_time):
            # memcached utilise 0 pour indiquer l'absence d'expiration.
            if exp_time is None:
                exp_time = 0
            else:
                exp_time = int(time.mktime(exp_time.timetuple()))
            return exp_time

        def set_cache(exp_time, key, flags):
            # Les erreurs sur le changement dans le cache sont ignorées
            # et la valeur positionnée est retournée à l'appelant.
            if self.__connection_cache:
                res = self.__connection_cache.set(key, pick_value, flags, exp_time)
                res.addErrback(self._eb)
                return res

        d_res = defer.Deferred()
        d = self.__get_connection()
        self.__connection_cache_deferred = d_res
        d.addCallback(lambda x:
            self.__connection_db_session.run(
                set_db,
                exp_time,
                transaction=transaction
            )
        )
        d.addCallback(prep_exp_time, exp_time)
        d.addCallback(set_cache, key, flags)
        d.addCallback(lambda x: d_res.callback(value))
        return d_res

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

        connected = False
        d_res = defer.Deferred()
        d = self.__get_connection()
        self.__connection_cache_deferred = d_res

        def get_from_cache(dummy):
            if self.__connection_cache:
                connected = True
                res = self.__connection_cache.get(key)
                res.addErrback(self._eb)
                return res
            return (0, None)
        d.addCallback(get_from_cache)

        def set_cache(instance, key, flags):
            # La valeur n'existait pas dans la base de données.
            if instance is None:
                # @TODO: retourner une Failure à la place ?
                return None

            exp_time = instance.expiration_date
            if exp_time is not None:
                # Si la valeur a une date de validité dans le passé,
                # on l'ignore. La valeur sera supprimée bientôt.
                if exp_time < datetime.now():
                    return None
                exp_time = int(time.mktime(exp_time.timetuple()))
            else:
                exp_time = 0

            result = pickle.loads(str(instance.value))
            if not connected:
                return result

            def set_in_cache(dummy):
                res = self.__connection_cache.set(key, instance.value, flags, exp_time)
                res.addErrback(self._eb)
                return res

            d3 = defer.succeed(None)
            d3.addCallback(set_in_cache)
            d3.addCallback(lambda x: result)
            return d3

        def check_result(result, key, txn, flags):
            # Le cache a renvoyé un résultat, on le retourne
            # à la fonction appelante.

            if result[-1] is not None:
                return pickle.loads(str(result[-1]))

            if not self.use_database:
                return None

            # Pas de résultat en cache, on interroge la base de données
            # et on met à jour le cache avec le résultat.
            d2 = self.__connection_db_session.run(
                DBSession.query(CorrelationContext).get, key,
                transaction=txn,
            )

            d2.addCallback(set_cache, key, flags)
            return d2

        d.addCallback(check_result, key, transaction, flags)
        d.addCallback(lambda res: d_res.callback(res))
        return d_res

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

        def delete_db(result, txn):
            return self.__connection_db_session.run(
                DBSession.query(
                    CorrelationContext
                ).filter(CorrelationContext.key == key).delete,
                transaction=txn,
            )

        def flush_db(nb_deleted, txn):
            d2 = self.__connection_db_session.run(
                DBSession.flush,
                transaction=transaction,
            )
            d2.addCallback(lambda res: nb_deleted)
            return d2

        # On supprime la clé 'key' et la valeur qui lui est associée du cache.
        d_res = defer.Deferred()
        d = self.__get_connection()
        self.__connection_cache_deferred = d_res

        def delete_cache(dummy):
            res = self.__connection_cache.delete(key)
            res.addErrback(self._eb)
            return res
        d.addCallback(delete_cache)

        if self.use_database:
            d.addCallback(delete_db, transaction)
            d.addCallback(flush_db, transaction)

        d.addCallback(lambda res: d_res.callback(res))
        return d_res

