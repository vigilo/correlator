# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""Règles de corrélation"""
from __future__ import absolute_import

from .datatypes import Named

class Rule(Named):
    """
    Classe définissant une règle du corrélateur Vigilo
    
    @cvar depends: liste des dépendances
    @type depends: C{list} (ou autre I{iterable})
    @ivar confkey: la clé utilisée pour référencer la règle dans le
        fichier C{settings.ini}.
    @type confkey: C{str}
    """

    depends = []

    def __init__(self, depends=None, confkey=None):
        """
        @param depends: liste des dépendances
        @type  depends: C{list} (ou autre I{iterable})
        @param confkey: la clé utilisée pour référencer la règle dans le
            fichier C{settings.ini}.
        @type  confkey: C{str}
        """
        super(Rule, self).__init__(self.__class__.__name__)
        if depends is not None:
            self.depends = depends
        if not isinstance(self.depends, (list, set, tuple)):
            raise TypeError("Rule dependencies must be iterable")
        self.confkey = confkey

