# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# pylint: disable-msg=C0111,W0212,R0904
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""Suite de tests pour la classe 'Api"""

import random
import threading
from datetime import datetime
import unittest
from nose.twistedtools import reactor, deferred
from twisted.internet import defer

from helpers import setup_mc, teardown_mc
from helpers import setup_db, teardown_db

from vigilo.models.session import DBSession
from vigilo.models.tables import Host, LowLevelService, StateName, \
                                    Dependency, DependencyGroup
from vigilo.correlator.topology import Topology
from vigilo.correlator.context import Context

class TestApiFunctions(unittest.TestCase):
    """
    Tests portant sur le contexte et l'API des règles de corrélation.

    Le setUp et le tearDown sont décorés par @deferred() pour que la création
    de la base soit réalisée dans le même threads que les accès dans les tests.
    """

    @deferred(timeout=30)
    def setUp(self):
        """Initialisation d'un contexte préalable à chacun des tests."""
        setup_mc()
        setup_db()
        return defer.succeed(None)

    @deferred(timeout=30)
    def tearDown(self):
        """Nettoyage du contexte à la fin de chaque test."""
        teardown_db()
        teardown_mc()
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
        DBSession.add(StateName(
            statename = u'OK',
            order = 0))
        DBSession.add(StateName(
            statename = u'UNKNOWN',
            order = 1))
        DBSession.add( StateName(
            statename = u'WARNING',
            order = 2))
        DBSession.add(StateName(
            statename = u'CRITICAL',
            order = 3))
        DBSession.add(StateName(
            statename = u'UP',
            order = 0))
        DBSession.add(StateName(
            statename = u'UNREACHABLE',
            order = 1))
        DBSession.add(StateName(
            statename = u'DOWN',
            order = 3))
        DBSession.flush()

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

        # On s'assure que la date de dernière mise à jour
        # de l'arbre topologique est bien nulle au départ.
        last_update = yield ctx.get('last_topology_update')
        self.assertEquals(last_update, None)

        # Instanciation de la topologie
        topology = Topology()

        # Calcul de la date courante
        date = datetime.now()

        # On vérifie que l'attribut 'topology' du
        # contexte renvoie bien une topologie similaire.
        ctx_topology = yield ctx.topology
        self.assertEquals(ctx_topology.nodes(), topology.nodes())
        self.assertEquals(ctx_topology.edges(), topology.edges())

        # On s'assure que la date de la mise à jour de l'arbre
        # topologique renseignée dans le contexte est bien
        # postérieure à la date calculée précédemment.
        last_update = yield ctx.last_topology_update
        self.assertTrue(last_update > date)
