# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# pylint: disable-msg=C0111,W0212,R0904,W0613,C0102
# Copyright (C) 2006-2012 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""Tests sur l'API des contextes de corrélation."""

import random
import unittest

from nose.twistedtools import reactor  # pylint: disable-msg=W0611
from nose.twistedtools import deferred

from twisted.internet import defer

from vigilo.correlator.test import helpers

from vigilo.correlator.context import Context
from vigilo.correlator.test.helpers import ConnectionStub, \
                                            MemcachedConnectionStub

from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)


class TestApiFunctions(unittest.TestCase):
    """
    Tests portant sur le contexte et l'API des règles de corrélation.

    Le setUp et le tearDown sont décorés par @deferred() pour que la création
    de la base soit réalisée dans le même threads que les accès dans les tests.
    """

    @deferred(timeout=60)
    def setUp(self):
        """Initialisation d'un contexte préalable à chacun des tests."""
        helpers.setup_db()
        return defer.succeed(None)

    @deferred(timeout=60)
    def tearDown(self):
        """Nettoyage du contexte à la fin de chaque test."""
        helpers.teardown_db()
        return defer.succeed(None)

    def test_contexts(self):
        """Création d'un contexte associé à un nom quelconque"""
        name = str(random.random())
        ctx = Context(name)
        assert ctx

    @deferred(timeout=60)
    @defer.inlineCallbacks
    def test_set_get(self):
        """set/get"""
        ctx = Context(42)
        ctx._connection = ConnectionStub()
        yield ctx.set("foo", "bar")
        foo = yield ctx.get("foo")
        self.assertEquals(foo, "bar")

    @deferred(timeout=60)
    @defer.inlineCallbacks
    def test_context_specific(self):
        """
        L'attribut classique est spécifique au contexte
        donc sa valeur n'est pas vue par les autres contextes.
        """
        ctx = Context(42)
        ctx._connection = ConnectionStub()
        yield ctx.set("foo", "bar")
        ctx2 = Context(43)
        ctx2._connection = ConnectionStub()
        foo = yield ctx2.get("foo")
        self.assertEquals(foo, None)

    @deferred(timeout=60)
    @defer.inlineCallbacks
    def test_delete(self):
        """La suppression doit fonctionner correctement"""
        ctx = Context(42)
        ctx._connection = ConnectionStub()
        yield ctx.set("foo", "bar")
        yield ctx.delete("foo")
        foo = yield ctx.get("foo")
        self.assertEquals(foo, None)

    @deferred(timeout=60)
    @defer.inlineCallbacks
    def test_shared_set_get(self):
        """set/get d'un attribut partagé"""
        ctx = Context(42)
        ctx._connection = ConnectionStub()
        yield ctx.setShared("foo", "bar")
        foo = yield ctx.getShared("foo")
        self.assertEquals(foo, "bar")

    @deferred(timeout=60)
    @defer.inlineCallbacks
    def test_shared_visibility(self):
        """Visibilité des attributs partagés"""
        ctx = Context(42)
        ctx._connection = ConnectionStub()
        yield ctx.setShared("foo", "bar")
        ctx2 = Context(43)
        ctx2._connection = ConnectionStub()
        foo = yield ctx2.getShared("foo")
        self.assertEquals(foo, "bar")
        yield ctx.deleteShared("foo")
        foo = yield ctx2.getShared("foo")
        self.assertEquals(foo, None)

    @deferred(timeout=60)
    def test_get_unicode(self):
        """Get sur le contexte (support d'unicode)"""
        ctx = Context(42)
        ctx._connection = MemcachedConnectionStub()
        def check(x):
            print repr(ctx._connection._cache.get.call_args)
            key = ctx._connection._cache.get.call_args[0][0]
            self.assertTrue(isinstance(key, str),
                    "Toutes les clés doivent être des str")
            self.assertEquals('vigilo%3A%C3%A9+%C3%A0+%C3%A8%3A42', key)
        d = ctx.get(u"é à è")
        d.addCallback(check)
        return d

    @deferred(timeout=60)
    def test_set_unicode(self):
        """Set sur le contexte (support d'unicode)"""
        ctx = Context(42)
        ctx._connection = MemcachedConnectionStub()
        def check(x):
            print repr(ctx._connection._cache.set.call_args)
            key = ctx._connection._cache.set.call_args[0][0]
            self.assertFalse(isinstance(key, unicode),
                    "Toutes les clés doivent être des str")
            self.assertEquals('vigilo%3A%C3%A9+%C3%A0+%C3%A8%3A42', key)
        d = ctx.set(u"é à è", "bar")
        d.addCallback(check)
        return d

    @deferred(timeout=60)
    def test_delete_unicode(self):
        """Delete sur le contexte (support d'unicode)"""
        ctx = Context(42)
        ctx._connection = MemcachedConnectionStub()
        def check(x):
            print repr(ctx._connection._cache.delete.call_args)
            key = ctx._connection._cache.delete.call_args[0][0]
            self.assertTrue(
                isinstance(key, str),
                "Toutes les clés doivent être des str")
            self.assertEquals('vigilo%3A%C3%A9+%C3%A0+%C3%A8%3A42', key)
        d = ctx.delete(u"é à è")
        d.addCallback(check)
        return d

    @deferred(timeout=60)
    def test_getshared_unicode(self):
        """Get partagé sur le contexte (support d'unicode)"""
        ctx = Context(42)
        ctx._connection = MemcachedConnectionStub()
        def check(x):
            print repr(ctx._connection._cache.get.call_args)
            key = ctx._connection._cache.get.call_args[0][0]
            self.assertTrue(
                isinstance(key, str),
                "Toutes les clés doivent être des str")
            self.assertEquals('shared%3A%C3%A9+%C3%A0+%C3%A8', key)
        d = ctx.getShared(u"é à è")
        d.addCallback(check)
        return d

    @deferred(timeout=60)
    def test_setShared_unicode(self):
        """Set partagé sur le contexte (support d'unicode)"""
        ctx = Context(42)
        ctx._connection = MemcachedConnectionStub()
        def check(x):
            print repr(ctx._connection._cache.set.call_args)
            key = ctx._connection._cache.set.call_args[0][0]
            self.assertTrue(
                isinstance(key, str),
                "Toutes les clés doivent être des str")
            self.assertEquals('shared%3A%C3%A9+%C3%A0+%C3%A8', key)
        d = ctx.setShared(u"é à è", "bar")
        d.addCallback(check)
        return d

    @deferred(timeout=60)
    def test_deleteshared_unicode(self):
        """Delete partagé sur le contexte (support d'unicode)"""
        ctx = Context(42)
        ctx._connection = MemcachedConnectionStub()
        def check(x):
            print repr(ctx._connection._cache.delete.call_args)
            key = ctx._connection._cache.delete.call_args[0][0]
            self.assertTrue(
                isinstance(key, str),
                "Toutes les clés doivent être des str, pas d'unicode")
            self.assertEquals('shared%3A%C3%A9+%C3%A0+%C3%A8', key)
        d = ctx.deleteShared(u"é à è")
        d.addCallback(check)
        return d
