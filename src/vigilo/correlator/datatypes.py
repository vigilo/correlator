# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2011-2013 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Définit un ensemble de types de données génériques.
"""

class Named(object):
    """Un object portant un nom."""

    def __init__(self, name):
        """
        Initialise un objet nommé.

        @param name: Nom de l'objet.
        @type name: C{str}
        """
        self.__name = name

    @property
    def name(self):
        """
        Renvoie le nom de l'objet courant.
        @rtype: C{str}
        """
        return self.__name


