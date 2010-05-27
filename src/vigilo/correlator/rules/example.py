# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""Exemple de module pour les règles de corrélation."""
from __future__ import absolute_import

from vigilo.correlator.rule import Rule

from vigilo.common.logging import get_logger
from vigilo.common.gettext import translate

LOGGER = get_logger(__name__)
_ = translate(__name__)

class ExampleRule(Rule):
    """Module d'exemple pour les règles de corrélation."""

    def __init__(self):
        """Initialisation du module."""
        super(ExampleRule, self).__init__([])

    def process(self, idnt, payload):
        """Traitement du message. Ici on se contente d'afficher une trace."""
        LOGGER.debug(_(u'id %(id)s payload %(payload)s'), {
                        "id": idnt,
                        "payload": payload,
                    })

def register(registry):
    """Enregistre le module."""
    registry.rules.register(ExampleRule())

