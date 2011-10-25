# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Context objects.
"""
__all__ = ( 'Context', )

from datetime import datetime

from twisted.internet import defer

from vigilo.common.conf import settings
from vigilo.common.logging import get_logger
from vigilo.common.gettext import translate

from vigilo.correlator.topology import Topology
from vigilo.correlator.db_thread import DummyDatabaseWrapper
from vigilo.correlator.memcached_connection import MemcachedConnection

LOGGER = get_logger(__name__)
_ = translate(__name__)

__all__ = ('Context', )

class NoTimeoutOverride(object):
    """
    Classe utilisée uniquement pour indiquer que le délai associé
    à une donnée n'a pas été surchargé localement lors d'un appel
    à L{Context.set} ou L{Context.setShared}.
    """
    pass

class Context(object):
    """
    Un contexte de corrélation pouvant recevoir des attributs arbitraires.

    Un certain nombre d'attributs sont prédéfinis et utilisés par le corrélateur
    pour alimenter la base de données.

    Les attributs prédéfinis sont :
        -   last_topology_update : date de dernière mise à jour
            de l'arbre topologique (L{datetime}).
        -   raw_event_id : identifiant de l'événement brut (C{int}).
        -   successors_aggregates : liste des identifiants des agrégats
            qui doivent être fusionnés avec celui de l'événement courant
            (C{list} of C{int}).
        -   predecessors_aggregates : liste des agrégats auxquels doit
            être rattaché l'événement (C{list} of C{int}).
        -   previous_state : état précédent du service (C{int}).
        -   statename : nom de l'état courant du service (C{str}).
        -   servicename : nom du service associé au contexte (C{str}).
        -   hostname : nom de l'hôte qui héberge le service (C{str}).
        -   impacted_hls : liste des identifiants des services de haut
            niveau impactés par l'événement (C{list} of C{int}).
        -   occurrences_count : nombre d'occurrences de l'alerte (C{int}).
        -   priority : priorité de l'événement corrélé (C{int}).
        -   no_alert : empêche la génération d'une alerte corrélée.
        -   payload : message brut (XML sérialisé) de l'événement reçu (C{str}).
    """

    def __init__(self, idxmpp, database, transaction=True, timeout=None):
        """
        Initialisation d'un contexte de corrélation (au moyen de MemcacheD).

        @param idxmpp: Identifiant XMPP de l'alerte brute
            reçue par le corrélateur.
        @type idxmpp: C{basestring}.
        """
        self._connection = MemcachedConnection()
        self._database = database
        self._transaction = transaction
        self._id = str(idxmpp)
        if timeout is None:
            timeout = settings['correlator'].as_float('context_timeout')
        self._timeout = timeout

    def topology(self):
        """
        Récupère la topologie associée à ce contexte.
        @rtype: L{defer.Deferred}.
        """
        topology = self._connection.get(
            'vigilo:topology',
            self._transaction,
        )

        def _generate(topo):
            LOGGER.debug("Re-generating the topology")
            return self._database.run(
                topo.generate,
                transaction=self._transaction
            )

        def _update_ctx(_dummy, topo):
            LOGGER.debug("Updating the cache with the new topology")
            dl = defer.DeferredList([
                self._connection.set(
                    'vigilo:topology',
                    topo,
                    transaction=self._transaction,
                ),
                self._connection.set(
                    'vigilo:last_topology_update',
                    datetime.now(),
                    transaction=self._transaction,
                ),
            ])
            dl.addCallback(lambda _dummy: topo)
            return dl

        def _check_existence(topo):
            LOGGER.debug("Current topology: %r", topo)
            if topo is None:
                topo = Topology()
                d = _generate(topo)
                d.addCallback(_update_ctx, topo)
                return d
            return topo

        topology.addCallback(_check_existence)
        return topology

    def last_topology_update(self):
        """
        Récupère la date de la dernière mise à jour de l'arbre topologique.
        @rtype: L{datetime}.
        """
        return self._connection.get(
            'vigilo:last_topology_update',
            self._transaction,
        )

    def get(self, prop):
        """
        Récupération de la valeur d'un des attributs du contexte.

        @param prop: Nom de l'attribut, tout identifiant Python valide
            est autorisé, sauf ceux dont le nom commence par '_'.
        @type prop: C{str}
        @return: Valeur de l'attribut demandé.
        @rtype: C{mixed}
        """
        # Les attributs pour lesquels il y a un getter
        # sont retournés en utilisant le getter.
        if prop in ('topology', 'last_topology_update'):
            return object.__getattribute__(self, prop)

        key = 'vigilo:%s:%s' % (prop, self._id)
        return self._connection.get(key.encode("utf8"),
                                    self._transaction)

    def set(self, prop, value, timeout=NoTimeoutOverride):
        """
        Modification dynamique d'un des attributs du contexte.

        @param prop: Nom de l'attribut, tout identifiant Python valide
            est autorisé, sauf ceux dont le nom commence par '_'.
        @type prop: C{str}
        @param value: Valeur à donner à l'attribut. La valeur doit
            être sérialisable à l'aide du module C{pickle} de Python.
        @type value: C{mixed}
        @param timeout: Durée de rétention (en secondes) de la donnée.
            Si omis, la durée de rétention globale associée au contexte
            est utilisée.
        @type timeout: C{float}
        """
        key = 'vigilo:%s:%s' % (prop, self._id)
        if timeout is NoTimeoutOverride:
            timeout = self._timeout
        return self._connection.set(
            key.encode("utf8"),
            value,
            self._transaction,
            time=timeout)

    def delete(self, prop):
        """
        Suppression dynamique d'un attribut du contexte.

        @param prop: Nom de l'attribut, tout identifiant Python valide
            est autorisé, sauf ceux dont le nom commence par '_'.
        @type prop: C{str}
        """
        key = 'vigilo:%s:%s' % (prop, self._id)
        return self._connection.delete(key.encode("utf8"),
                                       self._transaction)

    def getShared(self, prop):
        """
        Récupération de la valeur d'un des attributs partagés du contexte.

        @param prop: Nom de l'attribut partagé, tout identifiant Python valide
            est autorisé, sauf ceux dont le nom commence par '_'.
        @type prop: C{str}
        @return: Valeur de l'attribut partagé demandé.
        @rtype: C{mixed}
        """
        key = 'shared:%s' % prop
        return self._connection.get(key.encode("utf8"),
                                    self._transaction)

    def setShared(self, prop, value, timeout=NoTimeoutOverride):
        """
        Modification dynamique d'un des attributs partagés du contexte.

        @param prop: Nom de l'attribut partagé, tout identifiant Python valide
            est autorisé, sauf ceux dont le nom commence par '_'.
        @type prop: C{str}
        @param value: Valeur à donner à l'attribut partagé. La valeur doit
            être sérialisable à l'aide du module C{pickle} de Python.
        @type value: C{mixed}
        @param timeout: Durée de rétention (en secondes) de la donnée.
            Si omis, la durée de rétention globale associée au contexte
            est utilisée.
        @type timeout: C{float}
        """
        key = 'shared:%s' % prop
        if timeout is NoTimeoutOverride:
            timeout = self._timeout
        return self._connection.set(
            key.encode("utf8"),
            value,
            self._transaction,
            time=timeout)

    def deleteShared(self, prop):
        """
        Suppression dynamique d'un attribut partagé du contexte.

        @param prop: Nom de l'attribut partagé, tout identifiant Python valide
            est autorisé, sauf ceux dont le nom commence par '_'.
        @type prop: C{str}
        """
        key = 'shared:%s' % prop
        return self._connection.delete(key.encode("utf8"),
                                       self._transaction)
