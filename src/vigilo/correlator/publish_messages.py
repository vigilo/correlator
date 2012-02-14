# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Fonctions permettant la publication de messages divers sur le bus.
"""

from time import mktime

from vigilo.connector.handlers import BusPublisher



class MessagePublisher(BusPublisher):


    def __init__(self, nagios_hls_host, publications):
        super(MessagePublisher, self).__init__(publications)
        self.nagios_hls_host = nagios_hls_host


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
        agrégats (alertes corrélées) dont l'id est passé en paramètre.

        @type aggregate_id_list: Liste de C{int}
        """
        # Création du message à publier sur le bus
        msg = { "type": "delaggr",
                "aggregates": aggregate_id_list,
                }
        return self.sendMessage(msg)


    def publish_state(self, info_dictionary):
        """
        Publie sur le bus un message d'état correspondant
        correspondant au infos passées en paramètre.

        @param info_dictionary: Dictionnaire contenant les informations
        extraites du message d'alerte reçu par le rule dispatcher.
        @type info_dictionary: C{dictionary}
        """
        # Création du message à publier sur le bus
        msg = { "type": "state" }

        msg["timestamp"] = int(mktime(info_dictionary["timestamp"].timetuple()))

        if not info_dictionary["host"]:
            info_dictionary["host"] = self.nagios_hls_host
        msg["host"] = info_dictionary["host"]

        if info_dictionary["service"]:
            msg["service"] = info_dictionary["service"]

        msg["state"] = info_dictionary["state"]
        msg["message"] = info_dictionary["message"]

        return self.sendMessage(msg)
