# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""Namespaces utilisés dans les messages circulant sur le bus XMPP"""

NS_STATES = 'http://www.projet-vigilo.org/xmlns/state1'
NS_AGGR = 'http://www.projet-vigilo.org/xmlns/aggr1'
NS_DELAGGR = 'http://www.projet-vigilo.org/xmlns/delaggr1'
NS_EVENTS = 'http://www.projet-vigilo.org/xmlns/event1'
NS_CORREVENTS = 'http://www.projet-vigilo.org/xmlns/correvent1'
NS_COMMAND = 'http://www.projet-vigilo.org/xmlns/command1'
NS_DOWNTIME = 'http://www.projet-vigilo.org/xmlns/downtime1'
NS_TICKET = 'http://www.projet-vigilo.org/xmlns/ticket1'

def namespaced_tag(ns, tag):
    """
    Retourne le nom qualifié (QName) d'une balise XML
    en vue de son utilisation dans lxml.

    @param ns: Espace de nom de la balise (namespace).
    @type ns: C{basestring}
    @param tag: Nom local de la balise (localName).
    @type tag: C{basestring}
    @return: Nom qualifié de la balise (QName).
    @rtype: C{unicode}
    """
    return u'{%s}%s' % (ns, tag)

