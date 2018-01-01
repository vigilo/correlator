# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2018 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Module de publication de messages divers vers le bus Vigilo.
"""

from vigilo.connector.handlers import BusPublisher


class MessagePublisher(BusPublisher):
    """
    Classe permettant d'envoyer certains types de messages
    sur le bus d'échange de Vigilo.
    """

    def __init__(self, publications):
        """
        Construit une nouvelle instance de publication des messages.
        """
        super(MessagePublisher, self).__init__(publications)


    def publish_aggregate(self, aggregate_id_list, event_id_list):
        """
        Publie sur le bus les agrégats (alertes corrélées) dont
        l'id est passé en paramètre, contenant les événements
        (alertes brutes) dont l'id est également passé en paramètre.

        @param aggregate_id_list: Liste des ids des agrégats à publier.
        @type  aggregate_id_list: Liste de C{int}
        @param event_id_list: Liste des événements faisant partie des agrégats
            à publier.
        @type  event_id_list: Liste de C{int}
        """
        # Création du message à publier sur le bus
        msg = { "type": "aggr",
                "aggregates": aggregate_id_list,
                "alerts": event_id_list,
                }
        return self.sendMessage(msg)


    def delete_published_aggregates(self, aggregate_id_list):
        """
        Publie sur le bus un message signifiant la suppression des
        agrégats (alertes corrélées) dont l'identifiant est passé
        en paramètre.

        @type aggregate_id_list: Liste de C{int}
        """
        # Création du message à publier sur le bus
        msg = { "type": "delaggr",
                "aggregates": aggregate_id_list,
                }
        return self.sendMessage(msg)
