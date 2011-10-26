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
    def test_context_topology(self):
        """Récupération de l'arbre topologique dans le contexte"""

        # Ajout des noms d'états dans la BDD
        populate_statename()

        # Création d'une topologie basique par l'ajout
        # de deux hôtes et d'une dépendance entre eux.
        host1 = Host(
            name = u'host1',
            checkhostcmd = u'check1',
            snmpcommunity = u'com1',
            hosttpl = u'tpl1',
            address = u'192.168.0.1',
            snmpport = 11,
            weight = 42,
        )
        DBSession.add(host1)
        DBSession.flush()
        host2 = Host(
            name = u'host2',
            checkhostcmd = u'check2',
            snmpcommunity = u'com2',
            hosttpl = u'tpl2',
            address = u'192.168.0.2',
            snmpport = 11,
            weight = 42,
        )
        DBSession.add(host2)
        DBSession.flush()
        dg = DependencyGroup(
            dependent=host1,
            operator=u'&',
            role=u'topology',
        )
        DBSession.add(dg)
        DBSession.flush()
        d = Dependency(group=dg, supitem=host2)
        DBSession.add(d)
        DBSession.flush()

        # Création d'un contexte
        ctx = Context(42)
        ctx._connection = Mock()
        ctx._connection.get.side_effect = lambda *a: defer.succeed(None)
        ctx._connection.set.side_effect = lambda *a, **kw: defer.succeed(None)

        # On s'assure que la date de dernière mise à jour
        # de l'arbre topologique est bien nulle au départ.
        last_update = yield ctx.last_topology_update()
        self.assertEquals(last_update, None)
        ctx._connection.get.assert_called_with(
                "vigilo:last_topology_update", ctx._transaction)

        # Instanciation de la topologie
        topology = Topology()

        # Calcul de la date courante
        date = datetime.now()

        # On vérifie que l'attribut 'topology' du
        # contexte renvoie bien une topologie similaire.
        ctx_topology = yield ctx.topology()
        self.assertEquals(ctx_topology.nodes(), topology.nodes())
        self.assertEquals(ctx_topology.edges(), topology.edges())
        set_calls = ctx._connection.set.call_args_list
        self.assertEqual(set_calls[0][0][0], "vigilo:topology")
        self.assertEqual(set_calls[1][0][0], "vigilo:last_topology_update")

        # On s'assure que la date de la mise à jour de l'arbre
        # topologique renseignée dans le contexte est bien
        # postérieure à la date calculée précédemment.
        ctx._connection.get.side_effect = lambda *a: defer.succeed(set_calls[1][0][1])
        last_update = yield ctx.last_topology_update()
        self.assertTrue(last_update > date)

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
