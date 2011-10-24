# -*- coding: utf-8 -*-
# pylint: disable-msg=C0111,W0212,R0904
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

import unittest
from datetime import datetime

from nose.twistedtools import reactor, deferred
from twisted.internet import defer
from mock import Mock

from vigilo.models import tables
from vigilo.models.session import DBSession
from vigilo.pubsub.xml import NS_EVENT
import helpers

class RuleDispatcherTestCase(unittest.TestCase):

    @deferred(timeout=30)
    def setUp(self):
        helpers.setup_db()
        helpers.populate_statename()
        self._insert_test_data()
        DBSession.flush()
        self.rd = helpers.RuleDispatcherStub()
        return defer.succeed(None)

    @deferred(timeout=30)
    def tearDown(self):
        helpers.teardown_db()
        return defer.succeed(None)

    def _insert_test_data(self):
        """Création de quelques dépendances dans la BDD."""
        host = tables.Host(
            name=u'server.example.com',
            checkhostcmd=u'halt',
            hosttpl=u'',
            address=u'127.0.0.1',
            snmpcommunity=u'public',
            snmpport=42,
            weight=42,
        )
        DBSession.add(host)
        DBSession.add(tables.LowLevelService(
            servicename=u'Load',
            host=host,
            weight=42,
        ))

        DBSession.add(tables.HighLevelService(
            servicename=u'Load',
            message=u'Ouch',
            warning_threshold=100,
            critical_threshold=80,
        ))
        DBSession.flush()


    @deferred(timeout=30)
    def test_recv_old_state(self):
        """Abandon du traitement d'un état ancien"""
        ts_old = "1239104006"
        ts_recent = "1239104042"
        ts_recent_dt = datetime.fromtimestamp(int(ts_recent))
        idsupitem = tables.SupItem.get_supitem("server.example.com", "Load")
        self.rd._do_correl = Mock(name="do_correl")
        self.rd._context_factory = Mock(name="context") # pas besoin ici
        # Insertion de l'état récent
        state = DBSession.query(tables.State).get(idsupitem)
        state.timestamp = ts_recent_dt
        # Création d'un message d'événement portant sur un SBN.
        xml = """
        <item id="4242">
            <event xmlns="%(xmlns)s">
                <timestamp>%(ts_old)s</timestamp>
                <host>server.example.com</host>
                <service>Load</service>
                <state>WARNING</state>
                <message>WARNING: Load average is above 4 (4.5)</message>
            </event>
        </item>
        """ % {'xmlns': NS_EVENT, "ts_old": ts_old}
        d = self.rd._processMessage(xml)

        def cb(result):
            self.assertEqual(DBSession.query(tables.Event).count(), 0,
                "L'événement ne doit pas avoir été inséré")
            self.assertEqual(DBSession.query(tables.EventHistory).count(), 0,
                "L'événement ne doit pas avoir d'historique")
            self.assertEqual(self.rd._do_correl.call_count, 0,
                "La correlation ne doit pas avoir été lancée")
        d.addCallback(cb)
        return d
