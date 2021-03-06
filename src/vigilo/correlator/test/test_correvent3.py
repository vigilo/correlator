# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# pylint: disable-msg=C0111,W0212,R0904
# Copyright (C) 2006-2020 CS GROUP - France
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Teste la gestion de l'état d'acquittement
des événements corrélés lorsque de nouveaux
événements bruts arrivent (#924).
"""

import time
from datetime import datetime
import unittest

from nose.twistedtools import reactor  # pylint: disable-msg=W0611
from nose.twistedtools import deferred
from twisted.internet import defer

from mock import Mock
from vigilo.correlator.test import helpers

from vigilo.models.session import DBSession
from vigilo.models.tables import Host, Event, CorrEvent, StateName
from vigilo.correlator.correvent import CorrEventBuilder
from vigilo.correlator.db_thread import DummyDatabaseWrapper

from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)



class TestCorrevents3(unittest.TestCase):

    @deferred(timeout=60)
    def setUp(self):
        """Initialise la BDD au début de chaque test."""
        super(TestCorrevents3, self).setUp()
        helpers.setup_db()
        helpers.populate_statename()
        self.forwarder = helpers.RuleDispatcherStub()
        self.context_factory = helpers.ContextStubFactory()
        self.corrbuilder = CorrEventBuilder(Mock(), DummyDatabaseWrapper(True))
        self.corrbuilder.context_factory = self.context_factory
        self.host = None
        return defer.succeed(None)

    @deferred(timeout=60)
    def tearDown(self):
        """Nettoie la BDD à la fin de chaque test."""
        super(TestCorrevents3, self).tearDown()
        helpers.teardown_db()
        self.context_factory.reset()
        return defer.succeed(None)


    def make_deps(self):
        self.host = Host(
            name = u'Host',
            snmpcommunity = u'com11',
            hosttpl = u'tpl11',
            address = u'192.168.0.11',
            snmpport = 11,
        )
        DBSession.add(self.host)
        DBSession.flush()


    @defer.inlineCallbacks
    def prepare_correvent(self, old_state, new_state, ack):
        old_state = unicode(old_state)
        new_state = unicode(new_state)

        # Ajoute les dépendances nécessaires au test.
        self.make_deps()

        ts = time.time()
        ctx = self.context_factory(42)
        info_dictionary = {
            'id': 42,
            #'timestamp': ts,
            'host': self.host.name,
            'service': u'',
            'state': new_state,
            'message': new_state,
        }
        info_dictionary['timestamp'] = datetime.utcfromtimestamp(int(ts + 1))

        # Création Event + CorrEvent.
        event = Event(
            idsupitem=self.host.idhost,
            timestamp=datetime.utcfromtimestamp(int(ts)),
            current_state=StateName.statename_to_value(old_state),
            message=old_state,
        )
        DBSession.add(event)

        correvent = CorrEvent(
            cause=event,
            priority=42,
            trouble_ticket=None,
            ack=ack,
            occurrence=42,
            timestamp_active=datetime.utcfromtimestamp(int(ts)),
        )
        DBSession.add(correvent)
        correvent.events.append(event)
        DBSession.flush()
        idcorrevent = correvent.idcorrevent

        # On passe par une DeferredList pour garantir l'exécution
        # de tous les Deferred comme étant un seul bloc logique.
        yield defer.DeferredList([
            ctx.set('hostname', self.host.name),
            ctx.set('servicename', ''),
            ctx.set('statename', new_state),
            ctx.set('raw_event_id', event.idevent),
            ctx.set('idsupitem', self.host.idhost),
            ctx.set('payload', None),
            ctx.set('timestamp', info_dictionary['timestamp']),
            ctx.setShared('open_aggr:%s' % self.host.idhost, idcorrevent)
        ])

        res = yield self.corrbuilder.make_correvent(info_dictionary)
        DBSession.flush()
        defer.returnValue( (res, idcorrevent) )


    @deferred(timeout=60)
    @defer.inlineCallbacks
    def test_ack(self):
        """
        L'état d'acquittement "Acknowledged" ne doit pas être perdu (#924).

        Si un événement a été marqué comme "Pris en compte" (mais pas Fermé)
        et qu'on reçoit une nouvelle notification de Nagios, on ne doit pas
        perdre l'état d'acquittement actuellement associé.
        """
        res, idcorrevent = yield self.prepare_correvent(
            'UNREACHABLE',
            'DOWN',
            CorrEvent.ACK_KNOWN
        )

        # Aucune erreur ne doit avoir été levée.
        self.assertNotEquals(res, None)

        # Le CorrEvent doit toujours être le même.
        LOGGER.debug('Checking the CorrEvent')
        db_correvent = DBSession.query(CorrEvent).one()
        self.assertEqual(db_correvent.idcorrevent, idcorrevent)

        # L'état d'acquittement ne doit pas avoir été modifié
        # et l'agrégat doit toujours être ouvert.
        self.assertEqual(db_correvent.ack, CorrEvent.ACK_KNOWN)
        ctx = self.context_factory(42)
        open_aggr = yield ctx.getShared('open_aggr:%s' % self.host.idhost)
        self.assertNotEquals(open_aggr, 0)
        defer.returnValue(None)


    @deferred(timeout=60)
    @defer.inlineCallbacks
    def test_reactivate_aaclosed(self):
        """
        L'état d'acquittement "AAClosed" doit être réinitialisé si nécessaire.

        Si un événement a été marqué comme "Pris en compte et fermé" (AAClosed)
        et qu'on reçoit une nouvelle notification de Nagios indiquant que le
        problème persiste, le CorrEvent DOIT être réenclenché.
        """
        res, idcorrevent = yield self.prepare_correvent(
            'UNREACHABLE',
            'DOWN',
            CorrEvent.ACK_CLOSED
        )

        # Aucune erreur ne doit avoir été levée.
        self.assertNotEquals(res, None)

        # Le CorrEvent doit toujours être le même.
        LOGGER.debug('Checking the CorrEvent')
        db_correvent = DBSession.query(CorrEvent).one()
        self.assertEqual(db_correvent.idcorrevent, idcorrevent)

        # L'état d'acquittement DOIT avoir été modifié
        # et l'agrégat doit toujours être ouvert.
        self.assertEqual(db_correvent.ack, CorrEvent.ACK_NONE)
        ctx = self.context_factory(42)
        open_aggr = yield ctx.getShared('open_aggr:%s' % self.host.idhost)
        self.assertNotEquals(open_aggr, 0)
        defer.returnValue(None)


    @deferred(timeout=60)
    @defer.inlineCallbacks
    def test_close_aaclosed(self):
        """
        Fermeture d'un événement marqué comme "Pris en compte et fermé".

        Si un événement a été marqué comme "Pris en compte et fermé" (AAClosed)
        et qu'on reçoit une nouvelle notification de Nagios indiquant que le
        problème a été corrigé, le CorrEvent DOIT être fermé pour de bon.
        """
        res, idcorrevent = yield self.prepare_correvent(
            'DOWN',
            'UP',
            CorrEvent.ACK_CLOSED
        )

        # Aucune erreur ne doit avoir été levée.
        self.assertNotEquals(res, None)

        # Le CorrEvent doit toujours être le même.
        LOGGER.debug('Checking the CorrEvent')
        db_correvent = DBSession.query(CorrEvent).one()
        self.assertEqual(db_correvent.idcorrevent, idcorrevent)

        # L'état d'acquittement DOIT être "AAClosed"
        # et l'agrégat ne doit plus être marqué comme "ouvert".
        self.assertEqual(db_correvent.ack, CorrEvent.ACK_CLOSED)
        ctx = self.context_factory(42)
        open_aggr = yield ctx.getShared('open_aggr:%s' % self.host.idhost)
        self.assertEqual(open_aggr, 0)
        defer.returnValue(None)
