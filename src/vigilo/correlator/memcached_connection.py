# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

""" Connexion au serveur MemcacheD. """

try:
    import cPickle as pickle
except ImportError:
    import pickle

import memcache as mc
from datetime import datetime
import time
from twisted.internet import task

from sqlalchemy.exc import OperationalError

from vigilo.common.conf import settings
from vigilo.common.logging import get_logger
from vigilo.common.gettext import translate

from vigilo.models.tables import CorrelationContext
from vigilo.models.session import DBSession

LOGGER = get_logger(__name__)
_ = translate(__name__)

__all__ = (
    'MemcachedConnectionError',
    'MemcachedConnection',
)

class MemcachedConnectionError(Exception):
    """Exception levée lorsque le serveur MemcacheD est inaccessible."""
    LOGGER.error(_('Unable to establish connection to '
        'MemcacheD server. Using a SQLite database instead.').decode('utf-8'))

class MemcachedConnection(object):
    """
    Classe gérant la connexion et les échanges avec
    le serveur MemcacheD. Hérite de la classe mc.
    """
    # @TODO: utiliser t.p.m.MemCacheProtocol à la place de cette classe.

     # Attribut statique de classe
    instance = None

    # Maximum de secondes au-delà duquel memcached
    # considère que l'expiration est une date absolue
    # dans le temps (timestamp Unix) et non relative.
    MAX_RELATIVE = 60 * 60 * 24 * 30

    CONTEXT_TIMER = 60.

    def __new__(cls):
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
            cls.instance.__connection_db_session = DBSession
            cls.instance.__expiration = task.LoopingCall(
                cls.instance.__remove_expired_contexts)

            # Le timer est réglé sur 0 dans les tests unitaires,
            # où nous n'avons pas besoin d'expirer les contextes.
            if cls.CONTEXT_TIMER:
                cls.instance.__expiration_defer = \
                    cls.instance.__expiration.start(cls.CONTEXT_TIMER)

        return cls.instance

    def __init__(self):
        """
        Initialisation de la connexion.
        """
        # Si vous devez initialiser des attributs, faîtes le dans __new__
        # et non dans __init__ : __new__ ne fera l'initialisation qu'une
        # fois (singleton). Dans __init__, l'attribut serait réinitialisé
        # à chaque récupération d'une instance.

    def __del__(self):
        """
        Destruction de la connexion à memcached.
        """
        if self.__connection_cache:
            self.__connection_cache.disconnect_all()
        self.__expiration.stop()
        self.__expiration_defer.cancel()

    def __convert_to_datetime(self, timestamp):
        if not timestamp:
            return None
        if timestamp > self.MAX_RELATIVE:
            return datetime.fromtimestamp(timestamp)
        return datetime.fromtimestamp(timestamp + time.time())

    def __remove_expired_contexts(self):
        now = datetime.now()
        nb_deleted = self.__connection_db_session.query(CorrelationContext
            ).filter(CorrelationContext.expiration_date < now).delete()
        LOGGER.debug(_('Deleted %(nb_deleted)d expired correlation contexts'), {
            'nb_deleted': nb_deleted,
        })

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

    def connect(self):
        """
        Établit la connexion.
        """

        # Clôture d'une éventuelle connection ouverte
        # précédemment et devenue inopérante.
        # pylint: disable-msg=E0203
        if self.__connection_cache:
            # Si la connexion est en fait encore active on ne fait rien.
            if self.__connection_cache.set('vigilo', 1, time=1):
                return
            self.__connection_cache.disconnect_all()

        # Récupération des informations de connection.
        host = settings['correlator']['memcached_host']
        port = settings['correlator'].as_int('memcached_port')
        conn_str = '%s:%d' % (host, port)

        # Paramètre de débogage.
        try:
            debug = settings['correlator'].as_bool('memcached_debug')
        except KeyError:
            debug = False

        # Établissement de la connexion.
        LOGGER.info(_("Establishing connection to MemcacheD server (%s)..."),
                    conn_str)
        self.__connection_cache = mc.Client([conn_str])
        self.__connection_cache.debug = debug
        self.__connection_cache.behaviors = {'support_cas': 1}

    def set(self, key, value, **kwargs):
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

        LOGGER.debug(_("Trying to set value '%(value)s' for key '%(key)s'."), {
                        'key': key,
                        'value': value,
                    })

        # On établit la connection au serveur Memcached si nécessaire.
        if not self.__connection_cache:
            self.connect()

        # On sérialise la valeur 'value' avant son enregistrement
        value = pickle.dumps(value)

        # On associe la valeur 'value' à la clé 'key'.
        exp_time = self.__convert_to_datetime(kwargs.pop('time', None))
        # @FIXME: la limite (5) devrait être rendue configurable.
        for i in xrange(5):
            try:
                instance = CorrelationContext(key=key)
                instance = self.__connection_db_session.merge(instance)
                instance.value = value
                instance.expiration_date = exp_time
                self.__connection_db_session.flush()
            except OperationalError, e:
                if not e.connection_invalidated:
                    raise e
            else:
                break

        # memcached utilise 0 pour indiquer l'absence d'expiration.
        if exp_time is None:
            exp_time = 0
        else:
            exp_time = int(time.mktime(exp_time.timetuple()))

        self.__connection_cache.set(key, value, time=exp_time, **kwargs)
        return 1


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

        LOGGER.debug(_("Trying to get the value of the key '%(key)s'."), {
                            'key': key,
                        })

        # On établit la connection au serveur Memcached si nécessaire.
        if not self.__connection_cache:
            self.connect()

        # On récupère la valeur associée à la clé 'key'.
        result = self.__connection_cache.get(key)

        # Pas de résultat ? On récupère l'information depuis
        # la base de données et on met à jour le cache.
        if not result:
            for i in xrange(5):
                try:
                    instance = self.__connection_db_session.query(
                                    CorrelationContext).get(key)
                    if not instance:
                        return None
                except OperationalError, e:
                    if not e.connection_invalidated:
                        raise e
                else:
                    break

            exp_time = instance.expiration_date
            if exp_time is not None:
                # Si la valeur a une date de validité dans le passé,
                # on l'ignore. La valeur sera supprimée bientôt.
                if exp_time < datetime.now():
                    return None
                exp_time = int(time.mktime(exp_time.timetuple()))
            else:
                exp_time = 0

            self.__connection_cache.set(key, instance.value, time=exp_time)
            result = instance.value

        # On "dé-sérialise" la valeur avant de la retourner
        return pickle.loads(str(result))

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

        LOGGER.debug(_("Trying to delete the key '%(key)s'."), {
                            'key': key,
                        })

        # On établit la connection au serveur Memcached si nécessaire.
        if not self.__connection_cache:
            self.connect()

        # On supprime la clé 'key' et la valeur qui lui est associée.
        self.__connection_cache.delete(key)

        for i in xrange(5):
            try:
                nb_deleted = self.__connection_db_session.query(CorrelationContext
                    ).filter(CorrelationContext.key == key).delete()
                self.__connection_db_session.flush()
            except OperationalError, e:
                if not e.connection_invalidated:
                    raise e
            else:
                break

        return nb_deleted
