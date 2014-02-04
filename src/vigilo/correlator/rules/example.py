# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2014 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>
# pylint: disable-msg=W0613
# W0613: Unused argument 'link'

"""Exemple de module pour les règles de corrélation."""
from __future__ import absolute_import

from vigilo.correlator.rule import Rule

from vigilo.common.logging import get_logger
from vigilo.common.gettext import translate

LOGGER = get_logger(__name__)
_ = translate(__name__)

class ExampleRule(Rule):
    """Module d'exemple pour les règles de corrélation."""

    depends = []

    def process(self, link, msg_id):
        """
        Traitement du message par la règle.
        Ici, on se contente d'afficher une trace.

        @param link: Objet servant de lien avec le dispatcher et pouvant
            par exemple être utilisé pour envoyer des messages sur le bus.
        @type link: C{vigilo.correlator.actors.rule_runner.RuleRunner}
        @param msg_id: Identifiant de l'alerte brute traitée.
        @type  msg_id: C{unicode}
        """
        ctx = self._get_context(msg_id)
        payload = ctx.get('payload')
        LOGGER.debug(_('id %(id)s payload %(payload)s'), {
                        "id": msg_id,
                        "payload": payload,
                    })
