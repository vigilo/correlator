# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""Règles de corrélation"""
from __future__ import absolute_import

from .datatypes import Named

class Rule(Named):
    """Classe définissant une règle du corrélateur Vigilo"""
    def __init__(self, deps = None):
        super(Rule, self).__init__(self.__class__.__name__)
        if not deps:
            deps = []
        self._deps = deps

    @property
    def dependancies(self):
        """Retourne les dépendances d'une règle"""
        return self._deps

