# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""Règles de corrélation"""
from __future__ import absolute_import

import types
from twisted.internet import reactor, threads
from vigilo.correlator.context import Context
from vigilo.correlator.datatypes import Named

class ThreadWrapper(object):
    def __init__(self, cls_or_obj):
        # S'agit-il d'une classe ?
        if isinstance(cls_or_obj, types.TypeType):
            self._obj = None
            self._cls = cls_or_obj
        # Sinon, il s'agit d'un objet.
        else:
            self._obj = cls_or_obj
            self._cls = None
        self._callable_objs = {}

    def __getattr__(self, attr):
        if attr in self._callable_objs:
            return self._callable_objs[attr]

        ret = getattr(self._obj, attr)
        if callable(ret):
            wrapper = self.FunctionWrapper(self, ret)
            self._callable_objs[attr] = wrapper
            return wrapper
        return ret

    def __call__(self, *args, **kwargs):
        if self._cls:
            self._obj = self._cls(*args, **kwargs)
        return self

    class FunctionWrapper(object):
        def __init__(self, parent, callable_obj):
            self._parent = parent
            self._callable = callable_obj

        def __call__(self, *args, **kwargs):
            return threads.blockingCallFromThread(
                reactor, self._callable, *args, **kwargs)

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

    _context_factory = ThreadWrapper(Context)
    _database = None

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

    def set_database(self, database):
        self._database = database

    def _get_context(self, xmpp_id, timeout=None):
        return self._context_factory(xmpp_id, transaction=False, timeout=timeout)
