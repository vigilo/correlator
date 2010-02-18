# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""Exemple de module pour les règles de corrélation."""
from __future__ import absolute_import

from vigilo.correlator.rule import Rule
from vigilo.correlator import rulesapi
from vigilo.correlator.libs import etree

from vigilo.common.logging import get_logger
from vigilo.common.gettext import translate

LOGGER = get_logger(__name__)
_ = translate(__name__)

class TestRule(Rule):
    """Module d'exemple pour les règles de corrélation."""

    def __init__(self):
        """Initialisation du module."""
        super(TestRule, self).__init__([])

    def process(self, api, idnt, payload):
        """Traitement du message. Ici on se content de conserver une trace."""
        LOGGER.debug(_('id %(id)s payload %(payload)s') % 
            {"id": idnt, "payload": etree.tostring(payload)})
        return rulesapi.ENOERROR

def register(registry):
    """Enregistre le module."""
    registry.rules.register(TestRule())


