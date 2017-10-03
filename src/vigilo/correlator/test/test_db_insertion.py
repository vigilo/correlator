# -*- coding: utf-8 -*-
# pylint: disable-msg=C0111,W0212,R0904
# Copyright (C) 2006-2016 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""Suite de tests des fonctions réalisant des insertions dans la BDD."""
from datetime import datetime
import unittest
import time

from vigilo.correlator.db_insertion import insert_event, insert_state, \
                                    OldStateReceived
from vigilo.correlator.test import helpers

from vigilo.models.demo import functions
from vigilo.models.tables import State, StateName, Event, SupItem, \
                            LowLevelService, Host
from vigilo.models.session import DBSession



class TestDbInsertion(unittest.TestCase):
    """Teste l'insertion de données dans la BDD."""


    def setUp(self):
        super(TestDbInsertion, self).setUp()
        helpers.setup_db()
        helpers.populate_statename()

    def tearDown(self):
        helpers.teardown_db()
        super(TestDbInsertion, self).tearDown()


    def make_dependencies(self):
        """Création de quelques dépendances dans la BDD."""
        host = functions.add_host(u'server.example.com')
        functions.add_lowlevelservice(host, u'Load')
        functions.add_highlevelservice(u'Load')

    def test_insert_lls_event(self):
        """Insertion d'un évènement brut concernant un SBN"""

        self.make_dependencies()

        # Création d'un message d'événement portant sur un SBN.
        info_dictionary = {
                "type": "event",
                "timestamp": datetime.fromtimestamp(1239104006),
                "host": "server.example.com",
                "service": "Load",
                "state": u"WARNING",
                "message": u"WARNING: Load average is above 4 (4.5)",
                }
        info_dictionary['idsupitem'] = SupItem.get_supitem(
            info_dictionary['host'],
            info_dictionary['service']
        )

        # Insertion de l'événement dans la BDD
        idevent = insert_event(info_dictionary)

        assert idevent is not None
        event = DBSession.query(Event).one()

        # Vérification des informations de l'événement dans la BDD.
        self.assertEqual(LowLevelService, type(event.supitem))
        self.assertEqual(1239104006, time.mktime(event.timestamp.timetuple()))
        self.assertEqual(u'server.example.com', event.supitem.host.name)
        self.assertEqual(u'Load', event.supitem.servicename)
        self.assertEqual(u'WARNING',
            StateName.value_to_statename(event.current_state))
        self.assertEqual(u'WARNING',
            StateName.value_to_statename(event.initial_state))
        self.assertEqual(u'WARNING',
            StateName.value_to_statename(event.peak_state))
        self.assertEqual(u'WARNING: Load average is above 4 (4.5)',
                            event.message)

        # Insertion de l'état dans la BDD
        state = DBSession.query(State).get(info_dictionary['idsupitem'])
        # le timestamp par défaut est plus récent et insert_state refusera la
        # mise à jour
        state.timestamp = info_dictionary['timestamp']
        insert_state(info_dictionary)

        # Vérification des informations de l'état dans la BDD.
        self.assertEqual(LowLevelService, type(state.supitem))
        self.assertEqual(1239104006, time.mktime(state.timestamp.timetuple()))
        self.assertEqual('server.example.com', state.supitem.host.name)
        self.assertEqual('Load', state.supitem.servicename)
        self.assertEqual('WARNING',
            StateName.value_to_statename(state.state))
        self.assertEqual('WARNING: Load average is above 4 (4.5)',
                            state.message)

    def test_insert_hls_event(self):
        """Insertion d'un évènement brut concernant un SHN"""

        self.make_dependencies()

        # Création d'un message d'événement portant sur un SHN.
        info_dictionary = {
                "type": "event",
                "timestamp": datetime.fromtimestamp(1239104006),
                "host": helpers.settings['correlator']['nagios_hls_host'],
                "service": "Load",
                "state": "WARNING",
                "message": "WARNING: Load average is above 4 (4.5)",
                }
        info_dictionary['idsupitem'] = SupItem.get_supitem(
            info_dictionary['host'],
            info_dictionary['service']
        )

        # Insertion de l'événement dans la BDD
        idevent = insert_event(info_dictionary)

        # Aucun événement ne doit être créé
        # pour les services de haut niveau.
        assert idevent is None

    def test_insert_host_event(self):
        """Insertion d'un évènement brut concernant un hôte"""

        self.make_dependencies()

        # Création d'un message d'événement portant sur un hôte.
        info_dictionary = {
                "type": "event",
                "timestamp": datetime.fromtimestamp(1239104006),
                "host": "server.example.com",
                "service": None,
                "state": u"DOWN",
                "message": u"DOWN: No ping response",
                }
        info_dictionary['idsupitem'] = SupItem.get_supitem(
            info_dictionary['host'], None,
        )

        # Insertion de l'événement dans la BDD
        idevent = insert_event(info_dictionary)

        assert idevent is not None
        event = DBSession.query(Event).one()

        # Vérification des informations de l'événement dans la BDD.
        self.assertEqual(Host, type(event.supitem))
        self.assertEqual(1239104006, time.mktime(event.timestamp.timetuple()))
        self.assertEqual(u'server.example.com', event.supitem.name)
        self.assertEqual(u'DOWN',
            StateName.value_to_statename(event.current_state))
        self.assertEqual(u'DOWN',
            StateName.value_to_statename(event.initial_state))
        self.assertEqual(u'DOWN',
            StateName.value_to_statename(event.peak_state))
        self.assertEqual(u'DOWN: No ping response',
                            event.message)

        # Insertion de l'état dans la BDD
        state = DBSession.query(State).get(info_dictionary['idsupitem'])
        # le timestamp par défaut est plus récent et insert_state refusera la
        # mise à jour
        state.timestamp = info_dictionary['timestamp']
        insert_state(info_dictionary)

        # Vérification des informations de l'état dans la BDD.
        self.assertEqual(Host, type(state.supitem))
        self.assertEqual(1239104006, time.mktime(state.timestamp.timetuple()))
        self.assertEqual('server.example.com', state.supitem.name)
        self.assertEqual('DOWN',
            StateName.value_to_statename(state.state))
        self.assertEqual('DOWN: No ping response', state.message)



    def test_insert_old_state(self):
        """Abandon de l'insertion d'un état ancien"""
        self.make_dependencies()
        ts_old = 1239104006
        ts_recent = 1239104042
        ts_recent_dt = datetime.fromtimestamp(ts_recent)
        idsupitem = SupItem.get_supitem("server.example.com", "Load")
        # Insertion de l'état récent
        state = DBSession.query(State).get(idsupitem)
        state.timestamp = ts_recent_dt
        # Création d'un message d'événement portant sur un SBN.
        info_dictionary = {
                "type": "event",
                "timestamp": datetime.fromtimestamp(ts_old),
                "host": "server.example.com",
                "service": "Load",
                "state": "WARNING",
                "message": "WARNING: Load average is above 4 (4.5)",
                }
        info_dictionary['idsupitem'] = SupItem.get_supitem(
            info_dictionary['host'],
            info_dictionary['service']
        )
        # Insertion de l'ancien événement dans la BDD
        result = insert_state(info_dictionary)
        self.assertTrue(isinstance(result, OldStateReceived))
        supitem = DBSession.query(SupItem).get(idsupitem)
        self.assertEqual(supitem.state.timestamp, ts_recent_dt)

