# -*- coding: utf-8 -*-
# vim:set expandtab tabstop=4 shiftwidth=4:
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""Graphe topologique"""

from vigilo.models.session import DBSession
from sqlalchemy.sql.expression import not_, and_, or_, desc

import networkx as nx

from vigilo.models.tables import Dependency, DependencyGroup
from vigilo.models.tables import Event, CorrEvent, StateName

from vigilo.common.logging import get_logger
from vigilo.common.gettext import translate

LOGGER = get_logger(__name__)
_ = translate(__name__)

class Topology(nx.DiGraph):
    """
    Graphe topologique représentant les dépendances entre les services de bas
    niveau. Hérite de la classe DiGraph de la librairie NEtworkX.
    """

    def __init__(self):
        nx.DiGraph.__init__(self)
        self.generate()

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
                        ).all()

        # On ajoute ces dépendances dans le graphe en tant qu'arcs.
        for dependency in dependencies:
            self.add_edge(dependency.idsupitem, dependency.iddependent)

    def get_first_predecessors_aggregates(self, item_id):
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

        # On vérifie que l'item fait bien partie de la topologie
        if item_id in self.nodes():
            # On parcourt la liste des prédécesseurs de l'item donné.
            for item in self.predecessors(item_id):
                # Pour chacun d'entre eux, on vérifie
                # s'ils sont la cause d'un agrégat ouvert.
                open_aggregate = get_open_aggregate(item, CorrEvent)
                # Si c'est le cas, l'agrégat est ajouté au résultat.
                if open_aggregate:
                    if not open_aggregate in first_predecessors_aggregates:
                        first_predecessors_aggregates.append(open_aggregate)
                # Dans le cas contraire, on applique récursivement
                # la méthode sur les prédécesseurs de ce prédécesseur.
                else:
                    open_aggregates = self.get_first_predecessors_aggregates(
                                                                        item)
                    for open_aggregate in open_aggregates:
                        if not open_aggregate in first_predecessors_aggregates:
                            first_predecessors_aggregates.append(
                                                                open_aggregate)

        return first_predecessors_aggregates

    def get_first_successors_aggregates(self, item_id):
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

        # On vérifie que l'item fait bien partie de la topologie
        if item_id in self.nodes():
            # On parcourt la liste des successeurs de l'item donné.
            for item in self.successors(item_id):
                # Pour chacun d'entre eux, on vérifie
                # s'ils sont la cause d'un agrégat ouvert.
                open_aggregate = get_open_aggregate(item, CorrEvent)
                # Si c'est le cas, l'agrégat est ajouté au résultat.
                if open_aggregate:
                    if not open_aggregate in first_successors_aggregates:
                        first_successors_aggregates.append(open_aggregate)
        return first_successors_aggregates


def get_last_event(item_id, *args):
    """
    Récupère dand la BDD le dernier événement associé à l'item donné.

    @param item_id: Identifiant de l'item sur lequel s'opère la recherche.
    @type item_id: C{int}
    @return: Un événement.
    @rtype: L{Event}
    """

    return DBSession.query(
                        *args
                    ).filter(Event.idsupitem == item_id
                    ).filter(not_(
                                  or_(
                                Event.current_state ==
                                    StateName.statename_to_value('OK'),
                                Event.current_state ==
                                    StateName.statename_to_value('UP')
                                ),
                            )
                    ).order_by(desc(Event.idevent)).first()

def get_open_aggregate(item_id, *args):
    """
    Récupère dans la BDD l'agrégat ouvert causé par l'item donné.

    @param item_id: Identifiant de l'item sur lequel s'opère la recherche.
    @type  item_id: C{int}
    @return: Un agrégat.
    @rtype: L{CorrEvent}
    """

    aggregate = DBSession.query(
                        *args
                    ).join(
                        (Event, CorrEvent.idcause == Event.idevent)
                    ).filter(Event.idsupitem == item_id
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
                    ).first()
    return aggregate
