# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""
Context objects.
"""
__all__ = ( 'Context', )

from datetime import datetime

from vigilo.common.logging import get_logger
from vigilo.common.gettext import translate

from vigilo.correlator.topology import Topology
from vigilo.correlator.memcached_connection import MemcachedConnection

LOGGER = get_logger(__name__)
_ = translate(__name__)

STATENAME_PREFIX = 'statename:'
PREVIOUS_STATE_PREFIX = 'prev-state:'
PRIORITY_PREFIX = 'priority:'
OCCURRENCES_PREFIX = 'occurrences:'
IMPACTED_HLS_PREFIX = 'hls:'
UPDATE_PREFIX = 'update:'
TOPOLOGY_PREFIX = 'topo:'
TOPOLOGY_LAST_UPDATE_PREFIX = 'topo-date:'
HOSTNAME_PREFIX = 'hostname:'
SERVICENAME_PREFIX = 'servicename:'
PREDECESSORS_AGGREGATES_PREFIX = 'pred-aggr:'
SUCCESSORS_AGGREGATES_PREFIX = 'suc-aggr:'
RAW_EVENT_ID_PREFIX = 'raw-id:'

class Context(object):
    """
    An object that persists in shared memory until it expires.

    Contexts are the privileged way to share state between rules.

    Data kept in memcached so far:
        - a buffer of alerts that we could aggregate
        - the id of our aggregate
        - a threshold that counts down to zero
        
    ***
    
    Expiration is only set in one place, which doesn't make much sense.
    Coordinating expirations would work with an absolute deadline,
    itself stored in memcached.
    Should Context be split?
    Arbitrary data isn't supported, should it?
    I'd rather stop short of trying to build an ORM on top of
    a non-transactional store.

    Arbitrary data is ungood, what about context states?
    SEC contexts have two states: existing or not.
    More state machinery can be done with boolean ops on contexts.
    Prelude contexts aren't even checked for existence.
    But the threshold can be used as a simple state tracker.
    
    """

    def __init__(self, idxmpp):
        """
        Initialisation d'un contexte de corrélation (au moyen de MemcacheD).

        @param idxmpp: Identifiant XMPP de l'alerte brute reçue par le corrélateur.
        @type idxmpp: C{basestring}.
        """

        self.__id = str(idxmpp)
        self.__connection = MemcachedConnection()

    def __get_priority(self):
        """
        Renvoie la priorité de l'évènement corrélé traité.
    
        @return: La priorité de l'évènement corrélé traité.
        @rtype: C{basestring}.
        """
        return self.__connection.get(PRIORITY_PREFIX + self.__id)
    
    def __set_priority(self, value):
        """
        Change la priorité de l'évènement corrélé traité.

        @param value: La valeur à affecter à la priorité de l'alerte.
        @type value: C{int}.
    
        @return: Un entier non nul en cas de succès de l'opération.
        @rtype: C{int}.
        """
        return self.__connection.set(PRIORITY_PREFIX + self.__id, value)
        
    priority = property(
                __get_priority,
                __set_priority)


    def __get_occurrences_count(self):
        """
        Renvoie le nombre d'occurrences de l'alerte.
    
        @return: Le nombre d'occurrences de l'alerte.
        @rtype: C{basestring}.
        """
        return self.__connection.get(OCCURRENCES_PREFIX + self.__id)

    def __set_occurrences_count(self, value):
        """
        Change le nombre d'occurrences de l'alerte.

        @param value: La valeur à affecter au nombre d'occurrences de 
        l'alerte.
        @type value: C{int}.
    
        @return: Un entier non nul en cas de succès de l'opération.
        @rtype: C{int}.
        """
        return self.__connection.set(OCCURRENCES_PREFIX + self.__id, value)

    occurrences_count = property(
                            __get_occurrences_count,
                            __set_occurrences_count)


    def __get_impacted_hls(self):
        """
        Renvoie la liste des services de haut niveau impactés.
    
        @return: La liste des services de haut niveau impactés.
        @rtype: C{list} of C{basestring}.
        """
        return self.__connection.get(IMPACTED_HLS_PREFIX + self.__id)

    def __set_impacted_hls(self, value):
        """
        Change la liste des services de haut niveau impactés.

        @param value: La valeur à affecter à la liste des services de haut 
        niveau impactés.
        @type value: C{list} of C{int}.
    
        @return: Un entier non nul en cas de succès de l'opération.
        @rtype: C{int}.
        """
        return self.__connection.set(IMPACTED_HLS_PREFIX + self.__id, value)
        
    impacted_hls = property(
                    __get_impacted_hls,
                    __set_impacted_hls)


    @property
    def topology(self):
        """
        Récupère la topologie associée à ce contexte.
    
        @return: La topologie associée à ce contexte.
        @rtype: L{vigilo.correlator.topology.Topology}.
        """
        topology = self.__connection.get(TOPOLOGY_PREFIX)
        if not topology:
            topology = Topology()   
            self.__connection.set(TOPOLOGY_PREFIX, topology)
            self.__set_last_topology_update(datetime.now())
        return topology

    def __get_hostname(self):
        """
        Récupère le nom de l'hôte associé à ce contexte.
    
        @return: Le nom de l'hôte associé à ce contexte.
        @rtype: C{basestring}.
        """
        return self.__connection.get(HOSTNAME_PREFIX + self.__id)

    def __set_hostname(self, value):
        """
        Change le nom de l'hôte associé à ce contexte.

        @param value: La valeur à affecter au nom de l'hôte associé à ce 
        contexte.
        @type value: C{int}.
    
        @return: Un entier non nul en cas de succès de l'opération.
        @rtype: C{int}.
        """
        return self.__connection.set(HOSTNAME_PREFIX + self.__id, value)
        
    hostname = property(
                    __get_hostname,
                    __set_hostname)


    def __get_servicename(self):
        """
        Récupère le nom du service associé à ce contexte.
    
        @return: Le nom du service associé à ce contexte.
        @rtype: C{basestring}.
        """
        return self.__connection.get(SERVICENAME_PREFIX + self.__id)

    def __set_servicename(self, value):
        """
        Change le nom du service associé à ce contexte.

        @param value: La valeur à affecter au nom du service associé à ce 
        contexte.
        @type value: C{int}.
    
        @return: Un entier non nul en cas de succès de l'opération.
        @rtype: C{int}.
        """
        return self.__connection.set(SERVICENAME_PREFIX + self.__id, value)
        
    servicename = property(
                    __get_servicename,
                    __set_servicename)


    def __get_statename(self):
        """
        Renvoie le nom de l'état courant du service.
    
        @return: Le nom de l'état courant du service.
        @rtype: C{basestring}.
        """
        return self.__connection.get(STATENAME_PREFIX + self.__id)

    def __set_statename(self, value):
        """
        Change le nom de l'état courant du service.

        @param value: La valeur à affecter au nom de l'état courant du 
        service.
        @type value: C{int}.
    
        @return: Un entier non nul en cas de succès de l'opération.
        @rtype: C{int}.
        """
        return self.__connection.set(STATENAME_PREFIX + self.__id, value)
        
    statename = property(
                    __get_statename,
                    __set_statename)

    def __get_previous_state(self):
        """
        Renvoie le précédent état du service.
    
        @return: Le précédent état du service.
        @rtype: C{basestring}.
        """
        return self.__connection.get(PREVIOUS_STATE_PREFIX + self.__id)

    def __set_previous_state(self, value):
        """
        Change le précédent état du service.

        @param value: La valeur à affecter au précédent état du service.
        @type value: C{int}.
    
        @return: Un entier non nul en cas de succès de l'opération.
        @rtype: C{int}.
        """
        return self.__connection.set(PREVIOUS_STATE_PREFIX + self.__id, value)
        
    previous_state = property(
                    __get_previous_state,
                    __set_previous_state)

    def __get_predecessors_aggregates(self):
        """
        Renvoie la liste des agrégats auxquels doit être rattaché l'événement.
    
        @return: La liste des agrégats auxquels doit être rattaché 
        l'événement.
        @rtype: C{list} of C{basestring}.
        """
        return self.__connection.get(
            PREDECESSORS_AGGREGATES_PREFIX + self.__id)

    def __set_predecessors_aggregates(self, value):
        """
        Modifie la liste des agrégats auxquels doit être rattaché l'événement.

        @param value: La valeur à affecter à la liste des agrégats auxquels 
        doit être rattaché l'événement.
        @type value: C{list} of C{int}.
    
        @return: Un entier non nul en cas de succès de l'opération.
        @rtype: C{int}.
        """
        return self.__connection.set(
            PREDECESSORS_AGGREGATES_PREFIX + self.__id, value)
        
    predecessors_aggregates = property(
                    __get_predecessors_aggregates,
                    __set_predecessors_aggregates)

    def __get_successors_aggregates(self):
        """
        Renvoie la liste des aggrégats devant être fusionnés avec celui de
        l'événement courant.
    
        @return: La liste des agrégats devant être fusionnés avec celui de
        l'événement courant.
        @rtype: C{list} of C{basestring}.
        """
        return self.__connection.get(SUCCESSORS_AGGREGATES_PREFIX + self.__id)

    def __set_successors_aggregates(self, value):
        """
        Modifie la liste des aggrégats devant être fusionnés avec celui de
        l'événement courant.

        @param value: La valeur à affecter à la liste des agrégats devant être 
        fusionnés avec celui de l'événement courant.
        @type value: C{list} of C{int}.
    
        @return: Un entier non nul en cas de succès de l'opération.
        @rtype: C{int}.
        """
        return self.__connection.set(
            SUCCESSORS_AGGREGATES_PREFIX + self.__id, value)
        
    successors_aggregates = property(
                    __get_successors_aggregates,
                    __set_successors_aggregates)

    def __get_raw_event_id(self):
        """
        Renvoie l'identifiant de l'événement brut.
    
        @return: L'identifiant de l'événement brut.
        @rtype: C{basestring}.
        """
        return self.__connection.get(RAW_EVENT_ID_PREFIX + self.__id)

    def __set_raw_event_id(self, value):
        """
        Change l'identifiant de l'événement brut.

        @param value: La valeur à affecter à l'identifiant de l'événement 
        brut.
        @type value: C{int}.
    
        @return: Un entier non nul en cas de succès de l'opération.
        @rtype: C{int}.
        """
        return self.__connection.set(RAW_EVENT_ID_PREFIX + self.__id, value)
        
    raw_event_id = property(
                            __get_raw_event_id,
                            __set_raw_event_id)

    def __get_last_topology_update(self):
        """
        Renvoie la date de dernière mise à jour de l'arbre topologique.
    
        @return: La date de dernière mise à jour de l'arbre topologique.
        @rtype: L{datetime.datetime}.
        """
        return self.__connection.get(TOPOLOGY_LAST_UPDATE_PREFIX)

    def __set_last_topology_update(self, value):
        """
        Change la date de dernière mise à jour de l'arbre topologique.

        @param value: La valeur à affecter à la date de dernière mise à jour 
        de l'arbre topologique.
        @type value: L{datetime.datetime}.
    
        @return: Un entier non nul en cas de succès de l'opération.
        @rtype: C{int}.
        """
        return self.__connection.set(TOPOLOGY_LAST_UPDATE_PREFIX, value)
        
    last_topology_update = property(
                            __get_last_topology_update,
                            __set_last_topology_update)

