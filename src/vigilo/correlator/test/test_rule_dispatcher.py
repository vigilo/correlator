# -*- coding: utf-8 -*-
# pylint: disable-msg=C0111,W0212,R0904
# Copyright (C) 2006-2014 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

import unittest
import time
from datetime import datetime

from nose.twistedtools import reactor  # pylint: disable-msg=W0611
from nose.twistedtools import deferred

from twisted.internet import defer
from mock import Mock

from vigilo.models import tables
from vigilo.models.session import DBSession
from vigilo.models.demo import functions
from vigilo.correlator.test import helpers

class RuleDispatcherTestCase(unittest.TestCase):

    @deferred(timeout=60)
    def setUp(self):
        helpers.teardown_db()
        helpers.setup_db()
        helpers.populate_statename()
        self._insert_test_data()
        DBSession.flush()
        self.rd = helpers.RuleDispatcherStub()
        return defer.succeed(None)

    @deferred(timeout=60)
    def tearDown(self):
        helpers.teardown_db()
        return defer.succeed(None)

    def _insert_test_data(self):
        """Création de quelques dépendances dans la BDD."""
        host = functions.add_host(u'server.example.com')
        functions.add_lowlevelservice(host, u'Load')
        functions.add_highlevelservice(u'Load')

    @deferred(timeout=60)
    def test_recv_old_state(self):
        """Abandon du traitement d'un état ancien"""
        ts_old = 1239104006
        ts_recent = 1239104042
        ts_recent_dt = datetime.fromtimestamp(int(ts_recent))
        idsupitem = tables.SupItem.get_supitem("server.example.com", "Load")
        self.rd._do_correl = Mock(name="do_correl")
        self.rd._context_factory = Mock(name="context") # pas besoin ici
        self.rd._commit = Mock(name="commit")
        # Insertion de l'état récent
        state = DBSession.query(tables.State).get(idsupitem)
        state.timestamp = ts_recent_dt
        # Création d'un message d'événement portant sur un SBN.
        msg = {
                "id": 4242,
                "type": "event",
                "timestamp": ts_old,
                "host": "server.example.com",
                "service": "Load",
                "state": "WARNING",
                "message": "WARNING: Load average is above 4 (4.5)",
                }
        d = self.rd._processMessage(msg)

        def cb(_result):
            self.assertEqual(DBSession.query(tables.Event).count(), 0,
                "L'événement ne doit pas avoir été inséré")
            self.assertEqual(DBSession.query(tables.EventHistory).count(), 0,
                "L'événement ne doit pas avoir d'historique")
            self.assertEqual(self.rd._do_correl.call_count, 0,
                "La correlation ne doit pas avoir été lancée")
        d.addCallback(cb)
        return d

    @deferred(timeout=60)
    def test_no_message(self):
        """
        Un message vide/absent ne doit pas générer d'erreur (cf. #1085).

        À la place, le texte du message doit être remplacé par la chaîne vide.
        """
        self.rd._do_correl = Mock(name="do_correl")
        self.rd._context_factory = Mock(name="context") # pas besoin ici
        self.rd._commit = Mock(name="commit")
        # Création d'un message d'événement portant sur un SBN.
        msg = {
                "id": 4242,
                "type": "event",
                "timestamp": time.time() + 1,
                "host": "server.example.com",
                "service": "Load",
                "state": "WARNING",
                "message": None,
                }
        d = self.rd._processMessage(msg)

        def cb(result):
            event = DBSession.query(tables.Event).one()
            self.assertEqual(u'', event.message)
        d.addCallback(cb)
        return d
