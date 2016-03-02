# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2016 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Context objects.
"""
__all__ = ( 'Context', )

from vigilo.common.conf import settings
from vigilo.common.logging import get_logger
from vigilo.common.gettext import translate

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
        -   no_alert : empêche la génération d'une alerte corrélée (C{bool}).
        -   payload : message brut (XML sérialisé) de l'événement reçu (C{str}).
        -   idsupitem : identifiant de l'élément supervisé impacté (C{int}).
    """

    def __init__(self, msgid, transaction=True, timeout=None):
        """
        Initialisation d'un contexte de corrélation (au moyen de MemcacheD).

        @param msgid: Identifiant de l'alerte brute
            reçue par le corrélateur.
        @type msgid: C{basestring}.
        """
        self._connection = MemcachedConnection()
        self._transaction = transaction
        self._id = str(msgid)
        if timeout is None:
            timeout = settings['correlator'].as_float('context_timeout')
        self._timeout = timeout

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
        return self._connection.get(key, self._transaction)

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
            key,
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
        return self._connection.delete(key, self._transaction)

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
        return self._connection.get(key, self._transaction)

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
            key,
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
        return self._connection.delete(key, self._transaction)
