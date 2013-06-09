# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2013 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""

"""

# pylint: disable-msg=C0111,W0212,R0904,W0201
# - C0111: Missing docstring
# - W0212: Access to a protected member of a client class
# - R0904: Too many public methods
# - W0201: Attribute defined outside __init__


import time
from datetime import datetime
import unittest

from nose.twistedtools import reactor  # pylint: disable-msg=W0611
from nose.twistedtools import deferred

from twisted.internet import defer

from mock import Mock
from vigilo.correlator.test import helpers

from vigilo.models.session import DBSession
from vigilo.models.demo import functions
from vigilo.models import tables
from vigilo.correlator.correvent import CorrEventBuilder
from vigilo.correlator.db_thread import DummyDatabaseWrapper

from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)


class TestCorrevents5(unittest.TestCase):

    @deferred(timeout=60)
    def setUp(self):
        """Initialise la BDD au début de chaque test."""
        super(TestCorrevents5, self).setUp()
        helpers.setup_db()
        helpers.populate_statename()
        self.forwarder = helpers.RuleDispatcherStub()
        self.context_factory = helpers.ContextStubFactory()
        self.corrbuilder = CorrEventBuilder(Mock(), DummyDatabaseWrapper(True))
        self.corrbuilder.context_factory = self.context_factory
        self.make_deps()
        self.ts = int(time.time()) - 10
        return defer.succeed(None)

    @deferred(timeout=60)
    def tearDown(self):
        """Nettoie la BDD à la fin de chaque test."""
        super(TestCorrevents5, self).tearDown()
        helpers.teardown_db()
        self.context_factory.reset()
        return defer.succeed(None)


    def make_deps(self):
        """
        Création de 2 hôtes "Host 1" et "Host 2".
        """
        self.hosts = {}
        for i in xrange(1, 4 + 1):
            self.hosts[i] = functions.add_host(u'Host %d' % i)
            print "Added %s with ID #%d" % (
                self.hosts[i].name,
                self.hosts[i].idhost)
        print ""


    @defer.inlineCallbacks
    def handle_alert(self, host, new_state, preds=None, succs=None):
        """
        Simule l'arrivée d'une alerte concernant un hôte
        avec l'état donné en argument.
        """
        new_state = unicode(new_state)

        if preds is None:
            preds = []
        if succs is None:
            succs = []

        self.ts += 1
        info_dictionary = {
            'id': self.ts,
            #'timestamp': self.ts,
            'host': host.name,
            'service': u'',
            'state': new_state,
            'message': new_state,
        }
        info_dictionary['timestamp'] = datetime.fromtimestamp(self.ts)

        ctx = self.context_factory(self.ts)


        # Création Event.
        event = DBSession.query(tables.Event).filter(
            tables.Event.idsupitem == host.idhost).first()
        if event is None:
            event = tables.Event(idsupitem=host.idhost)

        event.current_state = tables.StateName.statename_to_value(
                                info_dictionary['state'])
        event.message = unicode(info_dictionary['message'])
        event.timestamp = info_dictionary['timestamp']
        DBSession.add(event)
        DBSession.flush()

        open_aggr = DBSession.query(
                tables.CorrEvent.idcorrevent
            ).filter(tables.CorrEvent.idcause == event.idevent
            ).scalar()
        # open_aggr vaut None si aucun événement corrélé
        # n'existe pour le moment pour l'élément.
        # Le contexte doit contenir 0 à la place pour ce cas.
        open_aggr = open_aggr or 0

        # On passe par une DeferredList pour garantir l'exécution
        # de tous les Deferred comme étant un seul bloc logique.
        yield defer.DeferredList([
            ctx.set('hostname', host.name),
            ctx.set('servicename', ''),
            ctx.set('statename', new_state),
            ctx.set('raw_event_id', event.idevent),
            ctx.set('idsupitem', host.idhost),
            ctx.set('payload', None),
            ctx.set('timestamp', info_dictionary['timestamp']),
            ctx.set('predecessors_aggregates', preds),
            ctx.set('successors_aggregates', succs),
            ctx.setShared('open_aggr:%s' % host.idhost, open_aggr),
        ])

        res = yield self.corrbuilder.make_correvent(info_dictionary)

        idcorrevent = DBSession.query(
                tables.CorrEvent.idcorrevent
            ).filter(tables.CorrEvent.idcause == event.idevent
            ).scalar()
        # Le expunge_all() évite que SQLAlchemy ne garde en cache
        # la valeur du .events des CorrEvents.
        DBSession.expunge_all()
        defer.returnValue( (res, idcorrevent) )


    @deferred(timeout=60)
    @defer.inlineCallbacks
    def test_reaggregate(self):
        """Réagrégation des événements corrélés (ordre alternatif)."""
        # Host 2 dépend de Host 1
        dep_group = functions.add_dependency_group(
                        self.hosts[2], None, u'topology', u'|')
        functions.add_dependency(dep_group, self.hosts[1], 1)

        # 1. Un 1er agrégat doit avoir été créé.
        LOGGER.debug('Step 1')
        res, idcorrevent1 = yield self.handle_alert(
            self.hosts[2], 'UNREACHABLE')
        # Aucune erreur n'a été levée.
        self.assertNotEquals(res, None)

        # 2. Un nouvel agrégat doit avoir été créé et l'agrégat
        #    précédent doit avoir été fusionné dans celui-ci.
        LOGGER.debug('Step 2')
        res, idcorrevent2 = yield self.handle_alert(
            self.hosts[1], 'DOWN', succs=[idcorrevent1])
        # Aucune erreur n'a été levée.
        self.assertNotEquals(res, None)

        # On a 2 événements bruts et 1 agrégat en base.
        LOGGER.debug("Checking events")
        self.assertEquals(2, DBSession.query(tables.Event).count())
        LOGGER.debug("Checking correvents")
        db_correvents = DBSession.query(tables.CorrEvent).all()
        self.assertEquals(1, len(db_correvents))

        # 3. L'agrégat de l'étape 2 doit avoir été désagrégé.
        LOGGER.debug('Step 3')
        res, idcorrevent3 = yield self.handle_alert(
            self.hosts[1], 'UP')
        # Aucune erreur n'a été levée.
        self.assertNotEquals(res, None)

        # On a 2 événements bruts et 2 agrégats en base.
        LOGGER.debug("Checking events")
        self.assertEquals(2, DBSession.query(tables.Event).count())
        LOGGER.debug("Checking correvents")
        db_correvents = DBSession.query(tables.CorrEvent).all()
        self.assertEquals(2, len(db_correvents))
        db_correvents.sort(key=lambda x: x.cause.supitem.name)
        # Le premier à l'état "UP" et porte sur "Host 1".
        self.assertEquals(self.hosts[1].idhost,
                          db_correvents[0].cause.idsupitem)
        self.assertEquals(
            u'UP',
            tables.StateName.value_to_statename(
                db_correvents[0].cause.current_state)
        )
        # Le 2nd est "UNREACHABLE" et porte sur "Host 2".
        self.assertEquals(self.hosts[2].idhost,
                          db_correvents[1].cause.idsupitem)
        self.assertEquals(
            u'UNREACHABLE',
            tables.StateName.value_to_statename(
                db_correvents[1].cause.current_state)
        )

        # 4. Les événements doivent avoir été réagrégés.
        LOGGER.debug('Step 4')
        # 3 = id du nouveau correvent après désagrégation
        res, idcorrevent4 = yield self.handle_alert(
            self.hosts[1], 'DOWN', succs=[3])
        # Aucune erreur n'a été levée.
        self.assertNotEquals(res, None)
        self.assertEquals(idcorrevent4, idcorrevent2)

        # On a 2 événements bruts et 1 agrégat en base.
        LOGGER.debug("Checking events")
        self.assertEquals(2, DBSession.query(tables.Event).count())
        LOGGER.debug("Checking correvents")
        db_correvents = DBSession.query(tables.CorrEvent).all()
        self.assertEquals(1, len(db_correvents))
        # Il a l'état "DOWN", porte sur "Host 1"
        # et contient les 2 événements bruts.
        self.assertEquals(self.hosts[1].idhost,
                          db_correvents[0].cause.idsupitem)
        self.assertEquals(
            u'DOWN',
            tables.StateName.value_to_statename(
                db_correvents[0].cause.current_state)
        )
        self.assertEquals(
            [u'Host 1', u'Host 2'],
            sorted([ev.supitem.name for ev in db_correvents[0].events])
        )

    @deferred(timeout=60)
    @defer.inlineCallbacks
    def test_reaggregate2(self):
        """Réagrégation des événements corrélés."""
        # Host 2 dépend de Host 1
        dep_group = functions.add_dependency_group(
                        self.hosts[2], None, u'topology', u'|')
        functions.add_dependency(dep_group, self.hosts[1], 1)

        # 1. Un 1er agrégat doit avoir été créé.
        LOGGER.debug('Step 1')
        res, idcorrevent1 = yield self.handle_alert(
            self.hosts[1], 'DOWN')
        # Aucune erreur n'a été levée.
        self.assertNotEquals(res, None)

        # 2. L'événement brut doit avoir été fusionné
        #    dans l'agrégat précédent.
        LOGGER.debug('Step 2')
        res, idcorrevent2 = yield self.handle_alert(
            self.hosts[2], 'UNREACHABLE', preds=[idcorrevent1])
        # Aucune erreur, mais correvent agrégé.
        self.assertEquals(res, None)
        self.assertEquals(idcorrevent2, None)

        # On a 2 événements bruts et 1 agrégat en base.
        LOGGER.debug("Checking events")
        self.assertEquals(2, DBSession.query(tables.Event).count())
        LOGGER.debug("Checking correvents")
        db_correvents = DBSession.query(tables.CorrEvent).all()
        self.assertEquals(1, len(db_correvents))

        # 3. L'agrégat de l'étape 2 doit avoir été désagrégé.
        LOGGER.debug('Step 3')
        res, idcorrevent3 = yield self.handle_alert(
            self.hosts[1], 'UP')
        # Aucune erreur n'a été levée.
        self.assertNotEquals(res, None)

        # On a 2 événements bruts et 2 agrégats en base.
        LOGGER.debug("Checking events")
        self.assertEquals(2, DBSession.query(tables.Event).count())
        LOGGER.debug("Checking correvents")
        db_correvents = DBSession.query(tables.CorrEvent).all()
        self.assertEquals(2, len(db_correvents))
        db_correvents.sort(key=lambda x: x.cause.supitem.name)
        # Le premier à l'état "UP" et porte sur "Host 1".
        self.assertEquals(self.hosts[1].idhost,
                          db_correvents[0].cause.idsupitem)
        self.assertEquals(
            u'UP',
            tables.StateName.value_to_statename(
                db_correvents[0].cause.current_state)
        )
        # Le 2nd est "UNREACHABLE" et porte sur "Host 2".
        self.assertEquals(self.hosts[2].idhost,
                          db_correvents[1].cause.idsupitem)
        self.assertEquals(
            u'UNREACHABLE',
            tables.StateName.value_to_statename(
                db_correvents[1].cause.current_state)
        )

        # 4. Les événements doivent avoir été réagrégés.
        LOGGER.debug('Step 4')
        # 2 = id du nouveau correvent après désagrégation
        res, idcorrevent4 = yield self.handle_alert(
            self.hosts[1], 'DOWN', succs=[2])
        # Aucune erreur n'a été levée.
        self.assertNotEquals(res, None)
        self.assertEquals(idcorrevent4, idcorrevent1)

        # On a 2 événements bruts et 1 agrégat en base.
        LOGGER.debug("Checking events")
        self.assertEquals(2, DBSession.query(tables.Event).count())
        LOGGER.debug("Checking correvents")
        db_correvents = DBSession.query(tables.CorrEvent).all()
        self.assertEquals(1, len(db_correvents))
        # Il a l'état "DOWN", porte sur "Host 1"
        # et contient les 2 événements bruts.
        self.assertEquals(self.hosts[1].idhost,
                          db_correvents[0].cause.idsupitem)
        self.assertEquals(
            u'DOWN',
            tables.StateName.value_to_statename(
                db_correvents[0].cause.current_state)
        )
        self.assertEquals(
            [u'Host 1', u'Host 2'],
            sorted([ev.supitem.name for ev in db_correvents[0].events])
        )

    @deferred(timeout=60)
    @defer.inlineCallbacks
    def test_aggregate_3_levels(self):
        """
        Agrégation sur 3 niveaux.
        """
        # Ajout des dépendances topologiques :
        # - Host 2 dépend de Host 1
        # - Host 3 dépend de Host 2
        dep_group = functions.add_dependency_group(
                        self.hosts[2], None, u'topology', u'|')
        functions.add_dependency(dep_group, self.hosts[1], 1)
        dep_group = functions.add_dependency_group(
                        self.hosts[3], None, u'topology', u'|')
        functions.add_dependency(dep_group, self.hosts[2], 1)
        functions.add_dependency(dep_group, self.hosts[1], 2)

        # Simule la chute de "Host 3" puis "Host 1", puis "Host 2".
        res, idcorrevent3 = yield self.handle_alert(self.hosts[3], 'UNREACHABLE')
        self.assertNotEquals(res, None)
        res, idcorrevent1 = yield self.handle_alert(self.hosts[1], 'DOWN')
        self.assertNotEquals(res, None)
        res, idcorrevent2 = yield self.handle_alert(
            self.hosts[2],
            'UNREACHABLE',
            preds=[idcorrevent1],
            succs=[idcorrevent3],
        )
        self.assertEquals(res, None) # Pas de nouvel agrégat créé.

        # On s'attend à trouver 3 événements bruts et 1 agrégat.
        self.assertEquals(3, DBSession.query(tables.Event).count())
        self.assertEquals(1, DBSession.query(tables.CorrEvent).count())

        events = DBSession.query(tables.Event).all()
        events.sort(key=lambda x: x.supitem.name)
        self.assertEquals(u'Host 1', events[0].supitem.name)
        self.assertEquals(u'Host 2', events[1].supitem.name)
        self.assertEquals(u'Host 3', events[2].supitem.name)

