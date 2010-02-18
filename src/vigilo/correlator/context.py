# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""
Context objects.
"""
__all__ = ( 'Context', )

from datetime import datetime

from vigilo.common.logging import get_logger
from vigilo.common.gettext import translate

from vigilo.correlator.topology import Topology

try:
    import cPickle as pickle
except ImportError:
    import pickle

LOGGER = get_logger(__name__)
_ = translate(__name__)

STATENAME_PREFIX = 'statename:'
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

    def __init__(self, conn, queue, idnt):
        """
        Represents a context object.

        conn is a memcached connection.
        queue is used to send alert messages.
        idnt is the context id, used to lookup an existing context or create a
        new one.

        “Represents” is in the ORM sense; the context may not actually exist
        on the memcached side, until you call get_or_create.
        """

        self.__conn = conn
        self.__queue = queue
        self.__id = str(idnt)

    @classmethod
    def get_or_create(cls, conn, queue, idnt):
        """
        Get, or if necessary create, a context.

        Some parameters are only used in the create case.
        They are passed to the constructor as is.

        Note: implementation-wise, the context object is always created.
        But in one case it refers to existing memcached data, in the other it
        creates the memcached data.
        """

        return cls(conn, queue, idnt)

    def __get_priority(self):
        """Renvoie la priorité de l'évènement corrélé traité."""
        result = self.__conn.get(PRIORITY_PREFIX + self.__id)
        if result is not None:
            return pickle.loads(result)
        return None
    def __set_priority(self, value):
        """Change la priorité de l'évènement corrélé traité."""
        res = self.__conn.set(
                        PRIORITY_PREFIX + self.__id, pickle.dumps(value))
        assert(res != 0)
    priority = property(
                __get_priority,
                __set_priority)

    def __get_occurrences_count(self):
        """Renvoie le nombre d'occurrences de l'alerte."""
        result = self.__conn.get(OCCURRENCES_PREFIX + self.__id)
        if result is not None:
            return pickle.loads(result)
        return None
    def __set_occurrences_count(self, value):
        """Change le nombre d'occurrences de l'alerte."""
        res = self.__conn.set(
                    OCCURRENCES_PREFIX + self.__id, pickle.dumps(value))
        assert(res != 0)
    occurrences_count = property(
                            __get_occurrences_count,
                            __set_occurrences_count)

    def __get_update_id(self):
        """Renvoie l'identifiant de mise à jour de l'alerte corrélée."""
        result = self.__conn.get(UPDATE_PREFIX + self.__id)
        if result is not None:
            return pickle.loads(result)
        return None
    def __set_update_id(self, value):
        """Change l'identifiant de mise à jour de l'alerte corrélée."""
        res = self.__conn.set(
                        UPDATE_PREFIX + self.__id, pickle.dumps(value))
        assert(res != 0)
    update_id = property(
                    __get_update_id,
                    __set_update_id)

    def __get_impacted_hls(self):
        """Renvoie la liste des services de haut niveau impactés."""
        value = self.__conn.get(IMPACTED_HLS_PREFIX + self.__id)
        if value is not None:
            return pickle.loads(value)
        return None
    def __set_impacted_hls(self, value):
        """Change la liste des services de haut niveau impactés."""
        res = self.__conn.set(
                        IMPACTED_HLS_PREFIX + self.__id, pickle.dumps(value))
        assert(res != 0)
    impacted_hls = property(
                    __get_impacted_hls,
                    __set_impacted_hls)

    @property
    def topology(self):
        """Get the topology associated with this context."""
        topology = self.__conn.get(TOPOLOGY_PREFIX)
        if not topology:
            topology = Topology()        
            self.__conn.add(TOPOLOGY_PREFIX, pickle.dumps(topology))
            self.__set_last_topology_update(datetime.now())
        else:
            topology = pickle.loads(topology)

        return topology

    def __get_hostname(self):
        """
        Get the name of the host of the service
        associated with this context.
        """
        result = self.__conn.get(HOSTNAME_PREFIX + self.__id)
        if result is not None:
            return pickle.loads(result)
        return None
    def __set_hostname(self, value):
        """
        Set the name of the host of the service
        associated with this context.
        """
        res = self.__conn.set(
                        HOSTNAME_PREFIX + self.__id, pickle.dumps(value))
        assert(res != 0)
    hostname = property(
                    __get_hostname,
                    __set_hostname)

    def __get_servicename(self):
        """Get the name of the service associated with this context."""
        result = self.__conn.get(SERVICENAME_PREFIX + self.__id)
        if result is not None:
            return pickle.loads(result)
        return None
    def __set_servicename(self, value):
        """Set the name of the service associated with this context."""
        res = self.__conn.set(
                    SERVICENAME_PREFIX + self.__id, pickle.dumps(value))
        assert(res != 0)
    servicename = property(
                    __get_servicename,
                    __set_servicename)

    def __get_statename(self):
        """Renvoie le nom de l'état courant du service."""
        result = self.__conn.get(STATENAME_PREFIX + self.__id)
        if result is not None:
            return pickle.loads(result)
        return None
    def __set_statename(self, value):
        """Change le nom de l'état courant du service."""
        res = self.__conn.set(
                        STATENAME_PREFIX + self.__id, pickle.dumps(value))
        assert(res != 0)
    statename = property(
                    __get_statename,
                    __set_statename)

    def __get_predecessors_aggregates(self):
        """
        Renvoie la liste des agrégats auxquels doit être rattaché l'événement.
        """
        result = self.__conn.get(PREDECESSORS_AGGREGATES_PREFIX + self.__id)
        if result is not None:
            return pickle.loads(result)
        return None
    def __set_predecessors_aggregates(self, value):
        """
        Modifie la liste des agrégats auxquels doit être rattaché l'événement.
        """
        res = self.__conn.set(PREDECESSORS_AGGREGATES_PREFIX +
                                self.__id, pickle.dumps(value))
        assert(res != 0)
    predecessors_aggregates = property(
                    __get_predecessors_aggregates,
                    __set_predecessors_aggregates)

    def __get_successors_aggregates(self):
        """
        Renvoie la liste des aggrégats devant être fusionnés avec celui de
        l'événement courant.
        """
        result = self.__conn.get(SUCCESSORS_AGGREGATES_PREFIX + self.__id)
        if result is not None:
            return pickle.loads(result)
        return None
    def __set_successors_aggregates(self, value):
        """
        Modifie la liste des aggrégats devant être fusionnés avec celui de
        l'événement courant.
        """
        res = self.__conn.set(
            SUCCESSORS_AGGREGATES_PREFIX + self.__id, pickle.dumps(value))
        assert(res != 0)
    successors_aggregates = property(
                    __get_successors_aggregates,
                    __set_successors_aggregates)

    def __get_raw_event_id(self):
        """Renvoie l'identifiant de l'événement brut."""
        result = self.__conn.get(RAW_EVENT_ID_PREFIX + self.__id)
        if result is not None:
            return pickle.loads(result)
        return None
    def __set_raw_event_id(self, value):
        """Change l'identifiant de l'événement brut."""
        res = self.__conn.set(
                        RAW_EVENT_ID_PREFIX + self.__id, pickle.dumps(value))
        assert(res != 0)
    raw_event_id = property(
                            __get_raw_event_id,
                            __set_raw_event_id)

    def __get_last_topology_update(self):
        """Renvoie la date de dernière mise à jour de l'arbre topologique."""
        result = self.__conn.get(TOPOLOGY_LAST_UPDATE_PREFIX)
        if result is not None:
            return pickle.loads(result)
        return None
    def __set_last_topology_update(self, value):
        """Change la date de dernière mise à jour de l'arbre topologique."""
        res = self.__conn.set(TOPOLOGY_LAST_UPDATE_PREFIX, pickle.dumps(value))
        assert(res != 0)
    last_topology_update = property(
                            __get_last_topology_update,
                            __set_last_topology_update)

