# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# pylint: disable-msg=C0111,W0212,R0904,W0613,C0102
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""Tests sur l'API des contextes de corrélation."""

import random
from datetime import datetime
import unittest

from nose.twistedtools import reactor, deferred
from twisted.internet import defer

from mock import Mock
from helpers import setup_db, teardown_db, populate_statename

from vigilo.models.session import DBSession
from vigilo.models.tables import Host, Dependency, DependencyGroup
from vigilo.correlator.topology import Topology
from vigilo.correlator.context import Context
from vigilo.correlator.test.helpers import ConnectionStub
from vigilo.correlator.db_thread import DummyDatabaseWrapper


class TestApiFunctions(unittest.TestCase):
    """
    Tests portant sur le contexte et l'API des règles de corrélation.

    Le setUp et le tearDown sont décorés par @deferred() pour que la création
    de la base soit réalisée dans le même threads que les accès dans les tests.
    """

    @deferred(timeout=30)
    def setUp(self):
        """Initialisation d'un contexte préalable à chacun des tests."""
        setup_db()
        return defer.succeed(None)

    @deferred(timeout=30)
    def tearDown(self):
        """Nettoyage du contexte à la fin de chaque test."""
        teardown_db()
        return defer.succeed(None)

    def test_contexts(self):
        """Création d'un contexte associé à un nom quelconque"""
        name = str(random.random())
        ctx = Context(name)
        assert ctx

    @deferred(timeout=30)
    @defer.inlineCallbacks
    def test_set_get(self):
        """set/get"""
        ctx = Context(42)
        ctx._connection = ConnectionStub()
        yield ctx.set("foo", "bar")
        foo = yield ctx.get("foo")
        self.assertEquals(foo, "bar")

    @deferred(timeout=30)
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

    @deferred(timeout=30)
    @defer.inlineCallbacks
    def test_delete(self):
        """La suppression doit fonctionner correctement"""
        ctx = Context(42)
        ctx._connection = ConnectionStub()
        yield ctx.set("foo", "bar")
        yield ctx.delete("foo")
        foo = yield ctx.get("foo")
        self.assertEquals(foo, None)

    @deferred(timeout=30)
    @defer.inlineCallbacks
    def test_shared_set_get(self):
        """set/get d'un attribut partagé"""
        ctx = Context(42)
        ctx._connection = ConnectionStub()
        yield ctx.setShared("foo", "bar")
        foo = yield ctx.getShared("foo")
        self.assertEquals(foo, "bar")

    @deferred(timeout=30)
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

    @deferred(timeout=30)
    def test_get_unicode(self):
        """Get sur le contexte (support d'unicode)"""
        ctx = Context(42)
        ctx._connection = ConnectionStub()
        ctx._connection.get = Mock()
        ctx._connection.get.side_effect = lambda *a: defer.succeed("x")
        def check(x):
            print repr(ctx._connection.get.call_args)
            arg = ctx._connection.get.call_args[0][0]
            self.assertFalse(isinstance(arg, unicode),
                    "Toutes les clés doivent être des str, pas d'unicode")
        d = ctx.get(u"é à è")
        d.addCallback(check)
        return d

    @deferred(timeout=30)
    def test_set_unicode(self):
        """Set sur le contexte (support d'unicode)"""
        ctx = Context(42)
        ctx._connection = ConnectionStub()
        ctx._connection._must_defer = True
        def check(x):
            for ctxkey in ctx._connection.data.keys():
                print repr(ctxkey)
                self.assertFalse(isinstance(ctxkey, unicode),
                        "Toutes les clés doivent être des str, pas d'unicode")
        d = ctx.set(u"é à è", "bar")
        d.addCallback(check)
        return d

    @deferred(timeout=30)
    def test_delete_unicode(self):
        """Delete sur le contexte (support d'unicode)"""
        ctx = Context(42)
        ctx._connection = ConnectionStub()
        ctx._connection.delete = Mock()
        ctx._connection.delete.side_effect = lambda *a: defer.succeed("x")
        def check(x):
            print repr(ctx._connection.delete.call_args)
            arg = ctx._connection.delete.call_args[0][0]
            self.assertFalse(isinstance(arg, unicode),
                    "Toutes les clés doivent être des str, pas d'unicode")
        d = ctx.delete(u"é à è")
        d.addCallback(check)
        return d

    @deferred(timeout=30)
    def test_getshared_unicode(self):
        """Get partagé sur le contexte (support d'unicode)"""
        ctx = Context(42)
        ctx._connection = ConnectionStub()
        ctx._connection.get = Mock()
        ctx._connection.get.side_effect = lambda *a: defer.succeed("x")
        def check(x):
            print repr(ctx._connection.get.call_args)
            arg = ctx._connection.get.call_args[0][0]
            self.assertFalse(isinstance(arg, unicode),
                    "Toutes les clés doivent être des str, pas d'unicode")
        d = ctx.getShared(u"é à è")
        d.addCallback(check)
        return d

    @deferred(timeout=30)
    def test_setShared_unicode(self):
        """Set partagé sur le contexte (support d'unicode)"""
        ctx = Context(42)
        ctx._connection = ConnectionStub()
        ctx._connection._must_defer = True
        def check(x):
            for ctxkey in ctx._connection.data.keys():
                print repr(ctxkey)
                self.assertFalse(isinstance(ctxkey, unicode),
                        "Toutes les clés doivent être des str, pas d'unicode")
        d = ctx.setShared(u"é à è", "bar")
        d.addCallback(check)
        return d

    @deferred(timeout=30)
    def test_deleteshared_unicode(self):
        """Delete partagé sur le contexte (support d'unicode)"""
        ctx = Context(42)
        ctx._connection = ConnectionStub()
        ctx._connection.delete = Mock()
        ctx._connection.delete.side_effect = lambda *a: defer.succeed("x")
        def check(x):
            print repr(ctx._connection.delete.call_args)
            arg = ctx._connection.delete.call_args[0][0]
            self.assertFalse(isinstance(arg, unicode),
                    "Toutes les clés doivent être des str, pas d'unicode")
        d = ctx.deleteShared(u"é à è")
        d.addCallback(check)
        return d
