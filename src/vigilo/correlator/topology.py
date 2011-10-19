# -*- coding: utf-8 -*-
# vim:set expandtab tabstop=4 shiftwidth=4:
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""Graphe topologique"""

from twisted.internet import defer

from vigilo.models.session import DBSession
from sqlalchemy.sql.expression import not_, and_, or_

import networkx as nx
import networkx.exception as nx_exc

from vigilo.models.tables import Dependency, DependencyGroup
from vigilo.models.tables import Event, CorrEvent, StateName

from vigilo.common.logging import get_logger
from vigilo.common.gettext import translate

LOGGER = get_logger(__name__)
_ = translate(__name__)

class Topology(nx.DiGraph):
    """
    Graphe topologique représentant les dépendances entre les services de bas
    niveau. Hérite de la classe DiGraph de la bibliothèque NetworkX.
    """

    def __init__(self):
        super(Topology, self).__init__()

    def generate(self):
        """Génère le graphe en récupérant les informations dans la BDD."""

        # On supprime tous les anciens noeuds et arcs du graphe.
        self.clear()

        # On récupère dans la BDD la liste des dépendances.
        dependencies = DBSession.query(
                            DependencyGroup.iddependent,
                            Dependency.idsupitem
                        ).join(
                            (Dependency, Dependency.idgroup == \
                                DependencyGroup.idgroup),
                        ).filter(DependencyGroup.role == u'topology'
                        ).all()

        # On ajoute ces dépendances dans le graphe en tant qu'arcs.
        for dependency in dependencies:
            self.add_edge(dependency.idsupitem, dependency.iddependent)

    def get_first_predecessors_aggregates(self, ctx, item_id):
        """
        Récupère les agrégats dont dépend l'item donné.
        La méthode cherche ainsi parmi les prédécesseurs de
        l'item ceux qui sont la cause d'un agrégat ouvert,
        et retourne ces agrégats (elle se limite au premier
        agrégat rencontré sur chaque branche de prédécesseurs).

        @param item_id: Identifiant de l'item sur lequel s'opère la recherche.
        @type item_id: C{int}
        @return: Liste de L{CorrEvent}.
        @rtype: List
        """
        first_predecessors_aggregates = []

        def _check_result(result, ctx, pred_id):
            # Aucun agrégat ouvert pour ce prédécesseur.
            # On s'appelle récursivement pour aller voir plus loin.
            if not result:
                return self.get_first_predecessors_aggregates(ctx, pred_id)
            return [result]

        try:
            # On parcourt la liste des prédécesseurs de l'item donné.
            predecessors = self.predecessors(item_id)
        except nx_exc.NetworkXError:
            # L'élément n'existait pas dans le graphe :
            # il n'y a donc pas d'agrégat prédécesseur ouvert.
            return defer.succeed([])

        if not predecessors:
            return defer.succeed([])

        for predecessor in predecessors:
            # Pour chacun d'entre eux, on vérifie
            # s'ils sont la cause d'un agrégat ouvert.
            d = get_open_aggregate(ctx, predecessor)
            d.addCallback(_check_result, ctx, predecessor)
            first_predecessors_aggregates.append(d)

        def _format_results(results):
            open_aggregates = set()
            for (res, idcorrevents) in results:
                if not res:
                    continue
                if not idcorrevents:
                    return []
                open_aggregates.update(set(idcorrevents))
            return list(open_aggregates)

        dl = defer.DeferredList(first_predecessors_aggregates)
        dl.addCallback(_format_results)
        return dl

    def get_first_successors_aggregates(self, ctx, item_id):
        """
        Récupère les agrégats dépendant de l'item donné.
        La méthode cherche ainsi parmi les successeurs de l'item ceux qui
        sont la cause d'un agrégat ouvert, et retourne ces agrégats (la
        recherche est limitée aux successeurs directs).

        @param item_id: Identifiant de l'item sur lequel s'opère la recherche.
        @type item_id: C{int}
        @return: Liste de L{CorrEvent}.
        @rtype: List
        """
        first_successors_aggregates = []
        try:
            for successor in self.successors(item_id):
                # Pour chacun d'entre eux, on vérifie
                # s'ils sont la cause d'un agrégat ouvert.
                first_successors_aggregates.append(
                    get_open_aggregate(ctx, successor)
                )

        except nx_exc.NetworkXError:
            # L'élément n'existait pas dans le graphe :
            # il n'y a donc pas d'agrégat successeur ouvert.
            return defer.succeed([])

        def _filter_results(results):
            open_aggregates = [idcorrevent for (res, idcorrevent) in results
                                if res and idcorrevent]
            # On retourne cette liste, privée des doublons.
            return list(set(open_aggregates))

        dl = defer.DeferredList(first_successors_aggregates)
        dl.addCallback(_filter_results)
        return dl


def get_open_aggregate(ctx, item_id):
    """
    Récupère dans le cache ou dans la BDD l'identifiant de l'événement
    corrélé (agrégat) ouvert et causé par l'élément supervisé donné.

    @param item_id: Identifiant de l'élément supervisé
        sur lequel s'opère la recherche.
    @type  item_id: C{int}
    @return: L'identifiant de l'agrégat ouvert ou None si aucun
        agrégat n'a été trouvé.
    @rtype: L{int} ou C{None}
    """
    d = defer.maybeDeferred(
        ctx.getShared,
        'open_aggr:%d' % item_id)

    def _fetch_db(result):
        # Si l'info se trouvait dans le cache,
        # on utilise cette valeur là.
        if result is not None:
            # La valeur 0 est utilisée à la place de None
            # dans le cache. On fait la conversion inverse ici.
            if not result:
                return None
            return result

        # Sinon on récupère l'information
        # depuis la base de données...
        aggregate = DBSession.query(
                CorrEvent.idcorrevent
            ).join(
                (Event, CorrEvent.idcause == Event.idevent)
            ).filter(
                not_(
                    and_(
                        or_(
                        Event.current_state ==
                            StateName.statename_to_value('OK'),
                        Event.current_state ==
                            StateName.statename_to_value('UP')
                        ),
                        CorrEvent.status == u'AAClosed'
                    )
                )
            ).filter(CorrEvent.timestamp_active != None
            ).filter(Event.idsupitem == item_id
            ).scalar()

        # ...et on met à jour le cache avant de retourner l'ID.
        # NB: la valeur 0 est utilisée à la place de None pour que
        # le cache puisse réellement servir à l'appel suivant.
        d2 = defer.maybeDeferred(
            ctx.setShared,
            'open_aggr:%d' % item_id,
            aggregate or 0)
        d2.addCallback(lambda _dummy, aggr: aggr, aggregate)
        return d2

    d.addCallback(_fetch_db)
    return d
