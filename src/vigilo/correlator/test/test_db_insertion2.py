# -*- coding: utf-8 -*-
# pylint: disable-msg=C0111,W0212,R0904
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""Suite de tests des fonctions réalisant des insertions dans la BDD."""
from datetime import datetime
import unittest
import time
from lxml import etree

from nose.twistedtools import reactor, deferred
from twisted.internet import defer

from vigilo.correlator.db_insertion import add_to_aggregate
from vigilo.correlator.db_thread import DummyDatabaseWrapper
import helpers

from vigilo.models.demo import functions
from vigilo.models.tables import State, StateName, Event, SupItem, \
                            LowLevelService, HighLevelService, Host, \
                            CorrEvent
from vigilo.models.session import DBSession

class TestDbInsertion2(unittest.TestCase):
    """Teste l'insertion de données dans la BDD."""

    @deferred(timeout=30)
    def setUp(self):
        super(TestDbInsertion2, self).setUp()
        helpers.setup_db()
        helpers.populate_statename()
        return defer.succeed(None)

    @deferred(timeout=30)
    def tearDown(self):
        helpers.teardown_db()
        super(TestDbInsertion2, self).tearDown()
        return defer.succeed(None)

    @deferred(timeout=30)
    @defer.inlineCallbacks
    def test_add_to_agregate(self):
        """Ajout d'un événement brut à un évènement corrélé déjà existant"""
        # On crée 2 couples host/service.
        host1 = functions.add_host(u'messagerie')
        service1 = functions.add_lowlevelservice(host1, u'Processes')
        service2 = functions.add_lowlevelservice(host1, u'CPU')

        # On ajoute 1 couple événement/agrégat à la BDD.
        event2 = functions.add_event(service2, u'WARNING', 'WARNING: CPU is overloaded')
        events_aggregate1 = functions.add_correvent([event2])

        # On ajoute un nouvel événement à la BDD.
        event1 = functions.add_event(service1, u'WARNING', 'WARNING: Processes are not responding')

        # On ajoute ce nouvel événement à l'agrégat existant.
        ctx = helpers.ContextStub(42)
        yield add_to_aggregate(
            event1.idevent,
            events_aggregate1.idcorrevent,
            DummyDatabaseWrapper(True),
            ctx,
            123,
            False
        )
        DBSession.flush()

        # On vérifie que l'événement a bien été ajouté à l'agrégat.
        DBSession.refresh(events_aggregate1)
        expected = sorted([event1.idevent, event2.idevent])
        actual = sorted([event.idevent for event in events_aggregate1.events])
        print "actual = %r, expected = %r" % (actual, expected)
        self.assertEquals(actual, expected)
