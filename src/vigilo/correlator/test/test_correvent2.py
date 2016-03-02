# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# pylint: disable-msg=C0111,W0212,R0904
# Copyright (C) 2006-2016 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

from datetime import datetime
import unittest

from nose.twistedtools import reactor  # pylint: disable-msg=W0611
from nose.twistedtools import deferred

from twisted.internet import defer

from mock import Mock
from vigilo.correlator.test import helpers

from vigilo.models.session import DBSession
from vigilo.models import tables
from vigilo.correlator.correvent import CorrEventBuilder
from vigilo.correlator.db_thread import DummyDatabaseWrapper

from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)



class TestAggregates(unittest.TestCase):

    @deferred(timeout=60)
    def setUp(self):
        """Initialisation avant chaque test."""
        super(TestAggregates, self).setUp()
        helpers.setup_db()
        helpers.populate_statename()
        self.forwarder = helpers.RuleDispatcherStub()
        self.context_factory = helpers.ContextStubFactory()
        self.corrbuilder = CorrEventBuilder(Mock(), DummyDatabaseWrapper(True))
        self.corrbuilder.context_factory = self.context_factory
        return defer.succeed(None)

    @deferred(timeout=60)
    def tearDown(self):
        """Finalisation après chaque test."""
        super(TestAggregates, self).tearDown()
        helpers.teardown_db()
        self.context_factory.reset()
        return defer.succeed(None)


    @deferred(timeout=60)
    @defer.inlineCallbacks
    def test_aggregation_scenario(self):
        """
        Scénario d'agrégation des événements corrélés (#910).
        """

        # Création de 4 hôtes.
        hosts = []
        for i in xrange(1, 5):
            hosts.append(tables.Host(
                name = u'Host éçà %d' % i,
                snmpcommunity = u'com11',
                hosttpl = u'tpl11',
                address = u'192.168.0.%d' % i,
                snmpport = 11,
            ))
            DBSession.add(hosts[i - 1])
        DBSession.flush()

        # Host1 et Host3 dépendent de Host2.
        # Host2 dépend de Host4.
        dg1 = tables.DependencyGroup(operator=u'|', role=u'topology',
                                     dependent=hosts[0])
        dg2 = tables.DependencyGroup(operator=u'|', role=u'topology',
                                     dependent=hosts[2])
        dg3 = tables.DependencyGroup(operator=u'|', role=u'topology',
                                     dependent=hosts[1])
        DBSession.add(dg1)
        DBSession.add(dg2)
        DBSession.add(dg3)

        DBSession.add(tables.Dependency(
            group=dg1,
            supitem=hosts[1],
            distance=1,
        ))
        DBSession.add(tables.Dependency(
            group=dg2,
            supitem=hosts[1],
            distance=1,
        ))
        DBSession.add(tables.Dependency(
            group=dg3,
            supitem=hosts[3],
            distance=1,
        ))
        DBSession.add(tables.Dependency(
            group=dg1,
            supitem=hosts[3],
            distance=2,
        ))
        DBSession.add(tables.Dependency(
            group=dg2,
            supitem=hosts[3],
            distance=2,
        ))
        DBSession.flush()

        correvents = []

        for i in xrange(1, 5):
            info_dictionary = {
                'id': i,
                'host': u'Host éçà %d' % i,
                'service': None,
                'state': u'DOWN',
                'timestamp': datetime.now(),
                'message': u'Host %d' % i,
            }

            event = tables.Event(
                idsupitem=hosts[i - 1].idhost,
                timestamp=info_dictionary['timestamp'],
                current_state=tables.StateName.statename_to_value(
                    info_dictionary['state']
                ),
                message=info_dictionary['message'],
            )
            DBSession.add(event)
            DBSession.flush()

            ctx = self.context_factory(i)
            defs = [
                ctx.set('hostname', hosts[i - 1].name),
                ctx.set('servicename', None),
                ctx.set('statename', 'DOWN'),
                ctx.set('raw_event_id', event.idevent),
                ctx.set('idsupitem', hosts[i - 1].idhost),
                ctx.set('payload', None),
                ctx.set('timestamp', info_dictionary['timestamp']),
                # Pas strictement requis, mais permet d'avoir toujours le même
                # résultat lors du test, quelle que soit la configuration.
                ctx.set('priority', 42),
            ]

            # Valeurs dans le contexte spécifiques à chaque message.
            if i == 1:
                is_update = False
                idcorrevent = 1
            elif i == 2:
                is_update = False
                idcorrevent = 2
                defs.append(ctx.set('successors_aggregates',
                        [correvents[0].idcorrevent]))
            elif i == 3:
                is_update = False
                idcorrevent = 2
                defs.append(ctx.set('predecessors_aggregates',
                        [correvents[1].idcorrevent]))
            else:
                is_update = False
                idcorrevent = i
                defs.append(ctx.set('successors_aggregates',
                        [correvents[1].idcorrevent]))

            # Prépare le contexte et appelle la fonction
            # de création/mise à jour de l'agrégat.
            yield defer.DeferredList(defs)
            yield self.corrbuilder.make_correvent(info_dictionary)
            DBSession.flush()

            correvent = DBSession.query(
                    tables.CorrEvent
                ).filter(tables.CorrEvent.idcause == event.idevent
                ).first()
            correvents.append(correvent)

            print self.corrbuilder.publisher.sendMessage.call_args_list

        # Il doit y avoir 1 seul agrégat, dont la cause est Host2
        # et qui contient 4 événements correspondant aux 4 hôtes.
        correvent = DBSession.query(tables.CorrEvent).one()
        self.assertEquals(hosts[3].idhost, correvent.cause.idsupitem)
        self.assertEquals(4, len(correvent.events))
