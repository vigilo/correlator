# -*- coding: utf-8 -*-
# pylint: disable-msg=C0111,W0212,R0904
# Copyright (C) 2006-2016 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""Suite de tests des fonctions réalisant des insertions dans la BDD."""
from datetime import datetime
import unittest
import time

from vigilo.correlator.db_insertion import insert_event
from vigilo.correlator.test import helpers

from vigilo.models.tables import StateName, Event, SupItem, Host, CorrEvent
from vigilo.models.session import DBSession

class TestDbInsertion3(unittest.TestCase):
    """Teste l'insertion de données dans la BDD."""

    def setUp(self):
        super(TestDbInsertion3, self).setUp()
        helpers.setup_db()
        helpers.populate_statename()

    def tearDown(self):
        helpers.teardown_db()
        super(TestDbInsertion3, self).tearDown()

    def make_dependencies(self):
        """Création de quelques dépendances dans la BDD."""
        host = Host(
            name=u'server.example.com',
            hosttpl=u'',
            address=u'127.0.0.1',
            snmpcommunity=u'public',
            snmpport=42,
        )
        DBSession.add(host)
        DBSession.flush()


    def test_reuse_event_with_no_correvent(self):
        """Ne pas créer de nouvel événement brut sans CorrEvent (#908)."""
        self.make_dependencies()
        host = DBSession.query(Host).first()
        ts = int(time.time())

        # On crée un événement brut, qu'on ne rattache
        # à aucun événement corrélé.
        DBSession.add(Event(
            supitem = host,
            current_state = StateName.statename_to_value(u'WARNING'),
            message = 'WARNING: ping',
            timestamp = datetime.fromtimestamp(ts - 42),
        ))
        DBSession.flush()

        # Préparation des informations du messages
        # et mise à jour de l'événement brut en base.
        info_dictionary = {
            'timestamp': datetime.fromtimestamp(ts),
            'host': host.name,
            'service': None,
            'state': u'CRITICAL',
            'message': u'CRITICAL: even worse',
            'idsupitem': SupItem.get_supitem(host.name, None)
        }
        insert_event(info_dictionary)

        # Aucun nouvel événement brut ne doit avoir été créé.
        event = DBSession.query(Event).one()
        # À la place, l'événement initial doit avoir été mis à jour.
        self.assertEquals(datetime.fromtimestamp(ts), event.timestamp)
        self.assertEquals(
            StateName.statename_to_value(u'CRITICAL'),
            event.current_state)
        self.assertEquals(
            StateName.statename_to_value(u'CRITICAL'),
            event.peak_state)
        self.assertEquals(
            StateName.statename_to_value(u'WARNING'),
            event.initial_state)
        self.assertEquals(info_dictionary['message'], event.message)


    def test_reuse_correvent_if_possible(self):
        """Privilégier la réutilisation des CorrEvents (#908)."""
        self.make_dependencies()
        host = DBSession.query(Host).first()
        ts = int(time.time())

        # On crée un événement brut, qu'on ne rattache
        # à aucun événement corrélé.
        DBSession.add(Event(
            supitem = host,
            current_state = StateName.statename_to_value(u'WARNING'),
            message = 'WARNING: ping',
            timestamp = datetime.fromtimestamp(ts - 42),
        ))
        DBSession.flush()

        # On crée un deuxième événement brut correspondant au même
        # élément supervisé, cette fois rattaché à un événement corrélé.
        event = Event(
            supitem = host,
            current_state = StateName.statename_to_value(u'WARNING'),
            message = 'WARNING: ping2',
            timestamp = datetime.fromtimestamp(ts - 21),
        )
        correvent = CorrEvent(
            cause = event,
            priority = 1,
            trouble_ticket = u'azerty1234',
            ack = CorrEvent.ACK_CLOSED,
            occurrence = 1,
            timestamp_active = datetime.fromtimestamp(ts - 21),
        )
        correvent.events = [event]
        DBSession.add(event)
        DBSession.add(correvent)
        DBSession.flush()

        # Préparation des informations du messages
        # et mise à jour de l'événement brut en base.
        info_dictionary = {
            'timestamp': datetime.fromtimestamp(ts),
            'host': host.name,
            'service': None,
            'state': u'CRITICAL',
            'message': u'CRITICAL: even worse',
            'idsupitem': SupItem.get_supitem(host.name, None)
        }
        insert_event(info_dictionary)

        # On doit toujours avoir 2 événements bruts en base.
        self.assertEquals(2, DBSession.query(Event).count())
        # On doit avoir un seul événement corrélé.
        correvent = DBSession.query(CorrEvent).one()
        # La cause de cet événement corrélé
        # doit toujours être la même.
        DBSession.refresh(event)
        self.assertEquals(event, correvent.cause)

        # L'événement brut associé à l'événement
        # corrélé doit avoir été mis à jour.
        self.assertEquals(datetime.fromtimestamp(ts), event.timestamp)
        self.assertEquals(
            StateName.statename_to_value(u'CRITICAL'),
            event.current_state)
        self.assertEquals(
            StateName.statename_to_value(u'CRITICAL'),
            event.peak_state)
        self.assertEquals(
            StateName.statename_to_value(u'WARNING'),
            event.initial_state)
        self.assertEquals(info_dictionary['message'], event.message)

        # L'autre événement brut ne doit pas avoir changé.
        event = DBSession.query(Event).filter(
            Event.idevent != event.idevent).one()
        self.assertEquals(datetime.fromtimestamp(ts - 42), event.timestamp)
        self.assertEquals(
            StateName.statename_to_value(u'WARNING'),
            event.current_state)
        self.assertEquals(
            StateName.statename_to_value(u'WARNING'),
            event.peak_state)
        self.assertEquals(
            StateName.statename_to_value(u'WARNING'),
            event.initial_state)
        self.assertEquals('WARNING: ping', event.message)
