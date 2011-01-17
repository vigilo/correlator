# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""Suite de tests pour la classe 'Api"""

import unittest

import random
import threading

from datetime import datetime

from vigilo.models.session import DBSession
from vigilo.models.tables import Host, LowLevelService, StateName, \
                                    Dependency, DependencyGroup
from vigilo.correlator.topology import Topology

from utils import setup_mc, teardown_mc
from utils import setup_db, teardown_db

from vigilo.correlator.context import Context

class TestApiFunctions(unittest.TestCase):
    """Tests portant sur le contexte et l'API des règles de corrélation."""

    def setUp(self):
        """Initialisation d'un contexte préalable à chacun des tests."""
        setup_mc()
        setup_db()

    def tearDown(self):
        """Nettoyage du contexte à la fin de chaque test."""
        teardown_db()
        teardown_mc()

    def test_contexts(self):
        """Création d'un contexte associé à un nom quelconque"""
        name = str(random.random())
        ctx = Context(name)
        assert ctx

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
        self.assertEquals(ctx.last_topology_update, None)

        # Instanciation de la topologie
        topology = Topology()

        # Calcul de la date courante
        date = datetime.now()

        # On vérifie que l'attribut 'topology' du
        # contexte renvoie bien une topologie similaire.
        self.assertEquals(ctx.topology.nodes(), topology.nodes())
        self.assertEquals(ctx.topology.edges(), topology.edges())

        # On s'assure que la date de la mise à jour de l'arbre
        # topologique renseignée dans le contexte est bien
        # postérieure à la date calculée précédemment.
        self.assertTrue(ctx.last_topology_update > date)
