# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Ce module contient une règle de corrélation qui empêche
de diminuer la priorité d'un événement.
Ceci permet en pratique de toujours voir la priorité
la plus importante reçue dans VigiBoard.
"""
from __future__ import absolute_import

from twisted.internet import defer
from sqlalchemy import not_ , and_

from vigilo.correlator.rule import Rule

from vigilo.common.logging import get_logger
from vigilo.common.gettext import translate
from vigilo.common.conf import settings

from vigilo.models.session import DBSession
from vigilo.models.tables import SupItem, CorrEvent, Event

LOGGER = get_logger(__name__)
_ = translate(__name__)

class PriorityMaxRule(Rule):
    """."""

    depends = ['PriorityRule']

    @defer.inlineCallbacks
    def process(self, link, xmpp_id, payload):
        """
        Traitement du message par la règle.

        @param link: Objet servant de lien avec le dispatcher et pouvant
            par exemple être utilisé pour envoyer des messages XML sur
            le bus XMPP.
        @type link: C{vigilo.correlator.actors.rule_runner.RuleRunner}
        @param xmpp_id: Identifiant XMPP de l'alerte brute traitée.
        @type xmpp_id: C{unicode}
        @param payload: Le message reçu par le corrélateur sur le bus XMPP.
        @type payload: C{unicode}
        """
        ctx = self._get_context(xmpp_id)
        hostname = yield ctx.get('hostname')
        servicename = yield ctx.get('servicename')
        priority = yield ctx.get('priority')

        item_id = SupItem.get_supitem(hostname, servicename)

        curr_priority = DBSession.query(
                CorrEvent.priority
            ).join(
                (Event, CorrEvent.idcause == Event.idevent),
                (SupItem, SupItem.idsupitem == Event.idsupitem),
            ).filter(SupItem.idsupitem == item_id
            ).filter(not_(and_(
                Event.current_state.in_([state_ok, state_up]),
                CorrEvent.status == u'AAClosed'
            ))
            ).filter(CorrEvent.timestamp_active != None
            ).scalar()

        if curr_priority is None:
            return

        if settings['correlator']['priority_order'] == 'asc':
            priority = min(priority, curr_priority)
        else:
            priority = max(priority, curr_priority)
        yield ctx.set('priority', priority)

