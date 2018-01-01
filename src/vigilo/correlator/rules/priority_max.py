# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2018 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>
# pylint: disable-msg=W0613
# W0613: Unused argument 'link'

"""
Ce module contient une règle de corrélation qui empêche
de diminuer la priorité d'un événement.
Ceci permet en pratique de toujours voir la priorité
la plus importante reçue dans VigiBoard.
"""
from __future__ import absolute_import

from sqlalchemy import not_ , and_

from vigilo.correlator.rule import Rule

from vigilo.common.logging import get_logger
from vigilo.common.gettext import translate
from vigilo.common.conf import settings

from vigilo.models.session import DBSession
from vigilo.models.tables import SupItem, CorrEvent, Event, StateName

LOGGER = get_logger(__name__)
_ = translate(__name__)

class PriorityMaxRule(Rule):
    """."""

    depends = ['PriorityRule']

    def process(self, link, msg_id):
        """
        Traitement du message par la règle.

        @param link: Objet servant de lien avec le dispatcher et pouvant
            par exemple être utilisé pour envoyer des messages sur le bus.
        @type link: C{vigilo.correlator.actors.rule_runner.RuleRunner}
        @param msg_id: Identifiant de l'alerte brute traitée.
        @type  msg_id: C{unicode}
        """
        ctx = self._get_context(msg_id)
        priority = ctx.get('priority')
        item_id = ctx.get('idsupitem')

        state_ok = StateName.statename_to_value(u'OK')
        state_up = StateName.statename_to_value(u'UP')
        curr_priority = self._database.run(
            DBSession.query(
                CorrEvent.priority
            ).join(
                (Event, CorrEvent.idcause == Event.idevent),
                (SupItem, SupItem.idsupitem == Event.idsupitem),
            ).filter(SupItem.idsupitem == item_id
            ).filter(
                not_(and_(
                    Event.current_state.in_([state_ok, state_up]),
                    CorrEvent.ack == CorrEvent.ACK_CLOSED
                ))
            ).scalar)

        if curr_priority is None or priority is None:
            return

        if settings['correlator']['priority_order'] == 'asc':
            priority = min(priority, curr_priority)
        else:
            priority = max(priority, curr_priority)
        ctx.set('priority', priority)
