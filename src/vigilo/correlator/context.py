# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""
Context objects.
"""
__all__ = ( 'Context', )

from datetime import datetime

from vigilo.common.conf import settings
settings.load_module(__name__)

from vigilo.common.logging import get_logger
from vigilo.common.gettext import translate

from vigilo.correlator.topology import Topology
from vigilo.correlator.memcached_connection import MemcachedConnection

LOGGER = get_logger(__name__)
_ = translate(__name__)

class Context(object):
    """
    Un contexte de corrélation pouvant recevoir des attributs plus ou moins
    arbitraires. Les attributs dont le nom commencent par '_' sont réservés
    à un usage strictement interne.

    Un certain nombre d'attributs sont prédéfinis et utilisés par le corrélateur
    pour alimenter la base de données.

    Les attributs prédéfinis sont :
        -   last_topology_update : date de dernière mise à jour
            de l'arbre topologique (L{datetime.datetime}).
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
    """

    def __init__(self, idxmpp, timeout=None):
        """
        Initialisation d'un contexte de corrélation (au moyen de MemcacheD).

        @param idxmpp: Identifiant XMPP de l'alerte brute
            reçue par le corrélateur.
        @type idxmpp: C{basestring}.
        """
        self.__connection = MemcachedConnection()
        self.__id = str(idxmpp)
        if timeout is None:
            timeout = settings['correlator'].as_float('context_timeout')
        self.__timeout = timeout

    @property
    def topology(self):
        """
        Récupère la topologie associée à ce contexte.
        @rtype: L{vigilo.correlator.topology.Topology}.
        """
        topology = self.__connection.get('vigilo:topology')
        if not topology:
            topology = Topology()
            self.__connection.set('vigilo:topology', topology)
            self.last_topology_update = datetime.now()
        return topology

    def __getattr__(self, prop):
        """
        Récupération de la valeur d'un des attributs du contexte.

        @param prop: Nom de l'attribut, tout identifieur Python valide
            est autorisé, sauf ceux dont le nom commence par '_'.
        @type prop: C{str}
        @return: Valeur de l'attribut demandé.
        @rtype: C{mixed}
        """
        if prop.startswith('_'):
            return object.__getattribute__(self, prop)
        return self.__connection.get(
            'vigilo:%s:%s' % (prop, self.__id))

    def __setattr__(self, prop, value):
        """
        Modification dynamique d'un des attributs du contexte.

        @param prop: Nom de l'attribut, tout identifieur Python valide
            est autorisé, sauf ceux dont le nom commence par '_'.
        @type prop: C{str}
        @param value: Valeur à donner à l'attribut. La valeur doit pouvoir
            être sérialisée à l'aide du module C{pickle} de Python.
        @type value: C{mixed}
        """
        if prop.startswith('_'):
            return object.__setattr__(self, prop, value)
        return self.__connection.set(
            'vigilo:%s:%s' % (prop, self.__id), value,
            time=self.__timeout)

    def __delattr__(self, prop):
        """
        Suppression dynamique d'un attribut du contexte.

        @param prop: Nom de l'attribut, tout identifieur Python valide
            est autorisé, sauf ceux dont le nom commence par '_'.
        @type prop: C{str}
        """
        if prop.startswith('_'):
            return object.__delattr__(self, prop)
        return self.__connection.delete(
            'vigilo:%s:%s' % (prop, self.__id))

