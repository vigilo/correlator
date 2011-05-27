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
from vigilo.correlator.memcached_connection import MemcachedConnection

LOGGER = get_logger(__name__)
_ = translate(__name__)

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
    """

    def __init__(self, idxmpp, timeout=None):
        """
        Initialisation d'un contexte de corrélation (au moyen de MemcacheD).

        @param idxmpp: Identifiant XMPP de l'alerte brute
            reçue par le corrélateur.
        @type idxmpp: C{basestring}.
        """
        self._connection = MemcachedConnection()
        self._id = str(idxmpp)
        if timeout is None:
            timeout = settings['correlator'].as_float('context_timeout')
        self._timeout = timeout

    @property
    @defer.inlineCallbacks
    def topology(self):
        """
        Récupère la topologie associée à ce contexte.
        @rtype: L{defer.Deferred}.
        """
        topology = yield defer.maybeDeferred(
            self._connection.get,
            'vigilo:topology'
        )

        if topology is None:
            topology = Topology()
            dl = defer.DeferredList([
                defer.maybeDeferred(
                    self._connection.set,
                    'vigilo:topology',
                    topology
                ),
                defer.maybeDeferred(
                    self._connection.set,
                    'vigilo:last_topology_update',
                    datetime.now()
                )
            ])
            cache = yield dl

        yield defer.returnValue(topology)

    @property
    def last_topology_update(self):
        """
        Récupère la date de la dernière mise à jour de l'arbre topologique.
        @rtype: L{datetime}.
        """
        return defer.maybeDeferred(
            self._connection.get,
            'vigilo:last_topology_update'
        )

    def get(self, prop):
        """
        Récupération de la valeur d'un des attributs du contexte.

        @param prop: Nom de l'attribut, tout identifieur Python valide
            est autorisé, sauf ceux dont le nom commence par '_'.
        @type prop: C{str}
        @return: Valeur de l'attribut demandé.
        @rtype: C{mixed}
        """
        # Les attributs pour lesquels il y a un getter
        # sont retournés en utilisant le getter.
        if prop in ('topology', 'last_topology_update'):
            return object.__getattribute__(self, prop)

        return defer.maybeDeferred(
            self._connection.get,
            'vigilo:%s:%s' % (prop, self._id),
        )

    def set(self, prop, value):
        """
        Modification dynamique d'un des attributs du contexte.

        @param prop: Nom de l'attribut, tout identifieur Python valide
            est autorisé, sauf ceux dont le nom commence par '_'.
        @type prop: C{str}
        @param value: Valeur à donner à l'attribut. La valeur doit pouvoir
            être sérialisée à l'aide du module C{pickle} de Python.
        @type value: C{mixed}
        """
        return defer.maybeDeferred(
            self._connection.set,
            'vigilo:%s:%s' % (prop, self._id),
            value,
            time=self._timeout
        )

    def delete(self, prop):
        """
        Suppression dynamique d'un attribut du contexte.

        @param prop: Nom de l'attribut, tout identifieur Python valide
            est autorisé, sauf ceux dont le nom commence par '_'.
        @type prop: C{str}
        """
        return defer.maybeDeferred(
            self._connection.delete,
            'vigilo:%s:%s' % (prop, self._id),
        )
