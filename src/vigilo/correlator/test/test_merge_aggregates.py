# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# pylint: disable-msg=C0111,W0212,R0904
# Copyright (C) 2006-2014 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Test de la fonction merge_aggregates.
"""

import unittest

from nose.twistedtools import reactor  # pylint: disable-msg=W0611
from nose.twistedtools import deferred

from twisted.internet import defer

from vigilo.correlator.db_insertion import merge_aggregates
from vigilo.correlator.db_thread import DummyDatabaseWrapper
from vigilo.correlator.test import helpers

from vigilo.models.session import DBSession
from vigilo.models.demo import functions
from vigilo.models.tables import CorrEvent

def create_topology_and_events():
    """
    Création de 4 couples host/service,
    4 événéments et 2 agrégats dans la BDD.
    """
    helpers.populate_statename()

    # On crée 4 couples host/service.
    host1 = functions.add_host(u'messagerie')
    service1 = functions.add_lowlevelservice(host1, u'Processes')
    service2 = functions.add_lowlevelservice(host1, u'CPU')
    service3 = functions.add_lowlevelservice(host1, u'RAM')
    service4 = functions.add_lowlevelservice(host1, u'Interface eth0')

    # On ajoute 4 événements et 2 agrégats dans la BDD.
    event1 = functions.add_event(
        service1,
        u'WARNING',
        'WARNING: Processes are not responding',
    )
    event2 = functions.add_event(
        service2,
        u'WARNING',
        'WARNING: CPU is overloaded',
    )
    event3 = functions.add_event(
        service3,
        u'WARNING',
        'WARNING: RAM is overloaded',
    )
    event4 = functions.add_event(
        service4,
        u'WARNING',
        'WARNING: eth0 is down',
    )

    events_aggregate1 = functions.add_correvent([event2, event1])
    events_aggregate2 = functions.add_correvent([event4, event3])

    return [[event1.idevent, event2.idevent, event3.idevent, event4.idevent],
            [events_aggregate1.idcorrevent, events_aggregate2.idcorrevent]]

class TestMergeAggregateFunction(unittest.TestCase):
    """Suite de tests de la fonction"""

    @deferred(timeout=60)
    def setUp(self):
        """Initialisation de la BDD préalable à chacun des tests"""
        helpers.setup_db()
        self.context_factory = helpers.ContextStubFactory()
        return defer.succeed(None)

    @deferred(timeout=60)
    def tearDown(self):
        """Nettoyage de la BDD à la fin de chaque test"""
        helpers.teardown_db()
        self.context_factory.reset()
        return defer.succeed(None)

    @deferred(timeout=60)
    def test_aggregates_merging(self):
        """Fusion de 2 agrégats"""

        # Création de 4 couples host/service,
        # 4 événéments et 2 agrégats dans la BDD.
        (events_id, aggregates_id) = create_topology_and_events()

        def _check(res, events_id):
            aggregate1 = DBSession.query(CorrEvent
                        ).filter(CorrEvent.idcorrevent == aggregates_id[0]
                        ).first()

            # On vérifie que l'agrégat 1 a bien été supprimé.
            self.assertTrue(aggregate1 is None)

            aggregate2 = DBSession.query(CorrEvent
                        ).filter(CorrEvent.idcorrevent == aggregates_id[1]
                        ).first()

            # On vérifie que la cause de l'agrégat 2
            # est toujours l'événement 4.
            self.assertTrue(aggregate2)
            self.assertEqual(aggregate2.idcause, events_id[3])

            events_id = [e.idevent for e in aggregate2.events]
            events_id.sort()

            # On vérifie que l'agrégat 2 regroupe
            # bien les événements 1, 2, 3 et 4.
            self.assertEqual(events_id,
                [events_id[0], events_id[1], events_id[2], events_id[3]])

            # On vérifie que le résultat retourné par la fonction
            # merge_aggregates est bien la liste des ids des
            # événements qui était auparavant rattachés à l'agrégat 1.
            res.sort()
            self.assertEqual(res, [events_id[0], events_id[1]])

        # On fusionne les 2 agrégats.
        d = merge_aggregates(
            aggregates_id[0],
            aggregates_id[1],
            DummyDatabaseWrapper(True),
            self.context_factory(42),
        )
        d.addCallback(_check, events_id)
        return d
