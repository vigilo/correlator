# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""
Fonctions permettant la publication de messages divers sur le bus XMPP.
"""

from twisted.words.xish import domish
from vigilo.correlator.xml import NS_AGGR, NS_DELAGGR, NS_STATES

from time import mktime

from vigilo.common.conf import settings

def publish_aggregate(forwarder, aggregate_id_list, event_id_list):
    """
    Publie sur le bus XMPP les agrégats (alertes corrélées) dont
    l'id est passé en paramètre, contenant les événements
    (alertes brutes) dont l'id est également passé en paramètre.
        
    @param queue: File sur laquelle sont
    envoyés les messages à publier sur le bus
    @type queue: ?
    @param aggregate_id_list: Liste des ids des agrégats à publier.
    @type aggregate_id_list: Liste de C{int}
    @param event_id_list: Liste des événements 
    faisant partie des agrégats à publier.
    @type event_id_list: Liste de C{int}
    """
    # Création d'une arborescence xml représentant
    # le message à publier sur le bus XMPP.
    pl = domish.Element((NS_AGGR, 'aggr'))
    
    # Création de la liste des agrégats
    aggregates = pl.addElement('aggregates')
    for aggregate_id in aggregate_id_list:
        aggregate = aggregates.addElement('aggregate')
        aggregate.addContent(str(aggregate_id))
    
    # Création de la liste des événements
    alerts = pl.addElement('alerts')
    for alert_id in event_id_list:
        alert = alerts.addElement('alert')
        alert.addContent(str(alert_id))
    
    forwarder.sendItem(pl.toXml())

def delete_published_aggregates(forwarder, aggregate_id_list):
    """
    Publie sur le bus XMPP un message signifiant la suppression des 
    agrégats (alertes corrélées) dont l'id est passé en paramètre.
        
    @param queue: File sur laquelle sont
    envoyés les messages à publier sur le bus
    @type queue: ?
    @param aggregate_id_list: Liste des ids des agrégats à supprimer.
    @type aggregate_id_list: Liste de C{int}
    """
    # Création d'une arborescence xml représentant
    # le message à publier sur le bus XMPP.
    pl = domish.Element((NS_DELAGGR, 'delaggr'))
    
    # Création de la liste des agrégats
    aggregates = pl.addElement('aggregates')
    for aggregate_id in aggregate_id_list:
        aggregate = aggregates.addElement('aggregate')
        aggregate.addContent(str(aggregate_id))

    forwarder.sendItem(pl.toXml())

def publish_state(forwarder, info_dictionary):
    """
    Publie sur le bus XMPP un message d'état correspondant
    correspondant au infos passées en paramètre.
        
    @param queue: File sur laquelle sont
    envoyés les messages à publier sur le bus.
    @type queue: ?
    @param info_dictionary: Dictionnaire contenant les informations 
    extraites du message d'alerte reçu par le rule dispatcher.
    @type info_dictionary: C{dictionary}
    """
    
    # Création d'une arborescence xml représentant
    # le message à publier sur le bus XMPP.
    pl = domish.Element((NS_STATES, 'state'))
    
    # Ajout de la balise timestamp
    tag = pl.addElement('timestamp')
    timestamp = mktime(info_dictionary["timestamp"].timetuple())
    tag.addContent(str(int(timestamp)))
        
    # Ajout de la balise host
    if not info_dictionary["host"]:
        info_dictionary["host"] = settings['correlator']['nagios_hls_host']
    tag = pl.addElement('host')
    tag.addContent(str(info_dictionary["host"]))
    
    if info_dictionary["service"]:
        # Ajout de la balise service
        tag = pl.addElement('service')
        tag.addContent(str(info_dictionary["service"]))
    
    # Ajout de la balise state
    tag = pl.addElement('state')
    tag.addContent(str(info_dictionary["state"]))
    
    # Ajout de la balise message
    tag = pl.addElement('message')
    tag.addContent(str(info_dictionary["message"]))
    
    forwarder.sendItem(pl.toXml())
