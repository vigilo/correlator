# -*- coding: utf-8 -*-
"""Teste le fonctionnement du rule dispatcher."""
import unittest
import transaction

from twisted.words.xish import domish
from vigilo.corr.xml import NS_EVENTS

from vigilo.models import HighLevelService, LowLevelService, Host, \
                            StateName, Dependency, Event, CorrEvent
from vigilo.models.configure import DBSession

from vigilo.corr.connect import connect
from vigilo.corr.libs import mp
from vigilo.corr.actors.rule_dispatcher import handle_bus_message
from vigilo.corr.actors import rule_runner

from vigilo.corr.registry import get_registry
from vigilo.corr.rules.hls_deps import HighLevelServiceDepsRule
from vigilo.corr.rules.lls_deps import LowLevelServiceDepsRule
from vigilo.corr.rules.update_attribute import UpdateAttributeRule
from vigilo.corr.rules.update_occurrences_count import \
                                        UpdateOccurrencesCountRule
from vigilo.corr.rules.priority import PriorityRule
from utils import setup_mc, teardown_mc, settings
from utils import setup_db, teardown_db

from vigilo.common.conf import settings


class TestRuleDispatcher(unittest.TestCase):
    """Classe de test du rule_dispatcher."""

    def register_rules(self):
        """Procède à l'enregistrement des règles à tester."""
        registry = get_registry()
        registry.rules.clear()

        registry.rules.register(HighLevelServiceDepsRule())
        registry.rules.register(LowLevelServiceDepsRule())
        registry.rules.register(UpdateAttributeRule())
        registry.rules.register(UpdateOccurrencesCountRule())
        registry.rules.register(PriorityRule())

    def generate_message(self, new_state, host_name, service_name=None):
        """
        Génère un message de changement d'état sur le
        bus XMPP concernant l'item passé en paramètre,
        et déclenche l'exécution du rule_dispatcher.
        """

        # On incrémente l'identifiant du message
        self.idnt += 1
        
        # On génère le message xml qui devrait être
        # reçu sur le bus XMPP dans un tel cas. 
        item = domish.Element((NS_EVENTS, 'item'))
        event = item.addElement((NS_EVENTS, 'event'))
        # Ajout de l'attribut id
        item['id'] = str(self.idnt)
        # Ajout de la balise timestamp
        tag = event.addElement('timestamp')
        tag.addContent("42")
        # Ajout de la balise host
        tag = event.addElement('host')
        if host_name:
            tag.addContent(host_name)
        else:
            tag.addContent(settings['correlator']['NAGIOS_HLS_HOST'])
        # Ajout de la balise service
        tag = event.addElement('service')
        tag.addContent(service_name)
        # Ajout de la balise state
        tag = event.addElement('state')
        tag.addContent(new_state)
        # Ajout de la balise message
        tag = event.addElement('message')
        tag.addContent(new_state)
        # Conversion en XML
        payload = item.toXml()
        
        # On "envoie" le message sur le bus
        self.manager.in_queue.put_nowait(payload)

        # On crée un pool de processus qui 
        # sera utilisé par le rule_dispatcher.
        rule_runner.api = None
        rule_runners_pool = mp.Pool(
                processes = 1,
                initializer = rule_runner.init,
                initargs = (self.manager.out_queue, )
        )
        
        # On lit le message sur le bus en utilisant la
        # fonction handle_bus_message du rule_dispatcher.
        handle_bus_message(self.manager, self.conn, None, None)
        
        rule_runners_pool.close()
        rule_runners_pool.join()


    def make_dependencies(self):
        """
        Ajoute des items (hôtes et services) dans 
        la BDD et crée des dépendances entre eux.
        """
        
        # Ajout d'états dans la BDD.
        DBSession.add(StateName(statename=u'OK', order=0))
        DBSession.add(StateName(statename=u'UP', order=0))
        DBSession.add(StateName(statename=u'UNKNOWN', order=0))
        DBSession.add(StateName(statename=u'WARNING', order=0))
        DBSession.add(StateName(statename=u'CRITICAL', order=0))
        DBSession.add(StateName(statename=u'UNREACHABLE', order=0))
        DBSession.add(StateName(statename=u'DOWN', order=0))
        DBSession.flush()
        
        # Ajout d'un hôte dans la BDD.
        self.host = Host(
            name = u'Host',
            checkhostcmd = u'check11',
            snmpcommunity = u'com11',
            hosttpl = u'tpl11',
            mainip = u'192.168.0.11',
            snmpport = 11,
            weight = 42,
        )
        DBSession.add(self.host)
        DBSession.flush()

        # Ajout de 4 service de bas niveau dans la BDD.
        self.lls1 = LowLevelService(
            servicename = u'LLS1',
            host = self.host,
            command = u'halt',
            op_dep = u'&',
            weight = 42,
        )
        DBSession.add(self.lls1)
        self.lls11 = LowLevelService(
            servicename = u'LLS11',
            host = self.host,
            command = u'halt',
            op_dep = u'&',
            weight = 42,
        )
        DBSession.add(self.lls11)
        self.lls12 = LowLevelService(
            servicename = u'LLS12',
            host = self.host,
            command = u'halt',
            op_dep = u'&',
            weight = 42,
        )
        DBSession.add(self.lls12)
        DBSession.flush()
        self.lls21 = LowLevelService(
            servicename = u'LLS21',
            host = self.host,
            command = u'halt',
            op_dep = u'&',
            weight = 42,
        )
        DBSession.add(self.lls21)

        # Ajout de 3 service de haut niveau dans la BDD.
        self.hls1 = HighLevelService(
                        servicename = u'HLS1', 
                        op_dep = u'&',
                        message = u'Foo', 
                        warning_threshold = 42,
                        critical_threshold = 42, 
                        weight = 42,
                        priority = 1)
        DBSession.add(self.hls1)
        self.hls11 = HighLevelService(
                        servicename = u'HLS11', 
                        op_dep = u'&',
                        message = u'Foo', 
                        warning_threshold = 42,
                        critical_threshold = 42, 
                        weight = 42,
                        priority = 1)
        DBSession.add(self.hls11)
        self.hls12 = HighLevelService(
                        servicename = u'HLS12', 
                        op_dep = u'&',
                        message = u'Foo', 
                        warning_threshold = 42,
                        critical_threshold = 42, 
                        weight = 42,
                        priority = 1)
        DBSession.add(self.hls12)
        DBSession.flush()

        # Ajout de dépendances :
        # - Entre HLS
        DBSession.add(Dependency(
                        supitem1 = self.hls1,
                        supitem2 = self.hls11))
        DBSession.add(Dependency(
                        supitem1 = self.hls1,
                        supitem2 = self.hls12))
        # - Entre HLS et LLS
        DBSession.add(Dependency(
                        supitem1 = self.hls11,
                        supitem2 = self.lls11))
        DBSession.add(Dependency(
                        supitem1 = self.hls11,
                        supitem2 = self.lls12))
        DBSession.add(Dependency(
                        supitem1 = self.hls12,
                        supitem2 = self.lls12))
        # - Entre LLS
        DBSession.add(Dependency(
                        supitem1 = self.lls1,
                        supitem2 = self.lls11))
        DBSession.add(Dependency(
                        supitem1 = self.lls1,
                        supitem2 = self.lls12))
        DBSession.add(Dependency(
                        supitem1 = self.lls11,
                        supitem2 = self.lls21))
        DBSession.add(Dependency(
                        supitem1 = self.lls12,
                        supitem2 = self.lls21))
        DBSession.flush()

    def setUp(self):
        """Initialise MemcacheD et la BDD au début de chaque test."""
        super(TestRuleDispatcher, self).setUp()
        setup_mc()
        setup_db()
        transaction.begin()

        # Insertion de données dans la base.
        self.make_dependencies()

        # Enregistrement des règles à tester.
        self.register_rules()

        # Instanciation d'un manager.
        self.manager = mp.Manager()
        self.manager.in_queue = mp.Queue()
        self.manager.out_queue = mp.Queue()
        
        # Instanciation d'une connection à MemCacheD.
        self.conn = connect()
        
        # Initialisation de l'identifiant des messages du bus.
        self.idnt = 0

    def tearDown(self):
        """Nettoie MemcacheD et la BDD à la fin de chaque test."""
        super(TestRuleDispatcher, self).tearDown()
        DBSession.flush()
        # Évite que d'anciennes instances viennent perturber le test suivant.
        DBSession.expunge_all()
        teardown_db()
        teardown_mc()

    def test_event_succession_1(self):
        """
        Teste le traitement d'une succession d'événements.
        
        LLS1 dépend de LLS11.
        
        On reçoit une première alerte sur LLS1.
        Puis une deuxième sur LLS11.
        Et enfin une nouvelle sur LLS1.
        """

        # Au départ, la table Event doit être vide.
        events = DBSession.query(Event).all()
        self.assertEqual(events, [])
    
        # On recoit sur le bus un message "WARNING" concernant lls1.
        self.generate_message("WARNING", self.host.name, 
                                self.lls1.servicename)
        event = DBSession.query(Event.idevent).one()
        idevent = event.idevent
        
        # TODO: Corriger le problème avec les sessions
        DBSession.add(self.host)
        DBSession.add(self.lls11)
    
        # On recoit sur le bus un message "WARNING" concernant lls11.
        self.generate_message("WARNING", self.host.name, 
                                self.lls11.servicename)
        
        # TODO: Corriger le problème avec les sessions
        DBSession.add(self.lls11)
        DBSession.add(self.host)
        
        # On récupère l'identifiant de cet événement.
        lls11_event = DBSession.query(Event.idevent
                    ).filter(Event.idsupitem == self.lls11.idservice
                    ).one()
    
        # TODO: Corriger le problème avec les sessions
        DBSession.add(self.lls1)
        
        # On recoit sur le bus un message "CRITICAL" concernant lls1.
        self.generate_message("CRITICAL", self.host.name, 
                                self.lls1.servicename)
        
        # TODO: Corriger le problème avec les sessions.
        DBSession.add(self.host)
        DBSession.add(self.lls1)
        
        # On compte le nombre d'événements dans la table Event.
        count = DBSession.query(Event).count()
        # Et on vérifie qu'il est bien égal à 2.
        self.assertEqual(count, 2)
#        # Et on vérifie qu'il est bien égal à 3.
#        self.assertEqual(count, 3)
        
        # On compte le nombre d'agrégats dans la table CorrEvent.
        aggregates = DBSession.query(CorrEvent
                    ).join((Event, Event.idevent == CorrEvent.idcause),)
        # Et on vérifie qu'il est bien égal à 1.
        self.assertEqual(aggregates.count(), 1)
        
        # On récupère l'aggrégat en question.
        aggregate = aggregates.one()
        # On vérifie que le nombre d'événements qu'il regroupe est bien 2.
        self.assertEqual(len(aggregate.events), 2)
#        # On vérifie que le nombre d'événements qu'il regroupe est bien 3.
#        self.assertEqual(len(aggregate.events), 3)
        # Et on s'asssure que c'est bien lls11 qui en est la cause.
        self.assertEqual(aggregate.idcause, lls11_event.idevent)
        
        # On récupère dans la BDD l'événement associé à lls1.
        event = DBSession.query(Event
                    ).filter(Event.idsupitem == self.lls1.idservice
                    ).one()
        # On vérifie que son id est toujours le même.
        self.assertEqual(event.idevent, idevent)
        # Et on s'assure qu'il fait bien partie de l'agrégat.
        self.assert_(idevent in [event.idevent for event in aggregate.events])
        
#       # On s'assure que l'événement associé
#       # à lls1 fait bien partie de l'agrégat.
#        self.assert_(idevent in [event.idevent for event in aggregate.events])

    def test_event_succession_2(self):
        """
        Teste le traitement d'une succession d'événements.
        
        LLS1 dépend de LLS11 et de LLS12.
        LLS11 et LLS12 dépendent de LLS21.
        
        On reçoit une première alerte sur LLS11, et une deuxième sur LLS12.
        Ensuite, une alerte arrive concernant LLS1.
        Puis, on reçoit une nouvelle alerte sur LLS1.
        Enfin, une alerte arrive sur LLS21 
        """

        # On recoit sur le bus un message "CRITICAL" concernant lls11.
        self.generate_message("CRITICAL", self.host.name, 
                                self.lls11.servicename)
        
        # TODO: Corriger le problème avec les sessions
        DBSession.add(self.host)
        DBSession.add(self.lls12)

        # On recoit sur le bus un message "CRITICAL" concernant lls12.
        self.generate_message("CRITICAL", self.host.name, 
                                self.lls12.servicename)
        
        # TODO: Corriger le problème avec les sessions
        DBSession.add(self.host)
        DBSession.add(self.lls1)

        # On recoit sur le bus un message "WARNING" concernant lls1.
        self.generate_message("WARNING", self.host.name, 
                                self.lls1.servicename)
        
        # TODO: Corriger le problème avec les sessions
        DBSession.add(self.lls1)
        
        # On compte le nombre d'événements dans la table Event.
        count = DBSession.query(Event).count()
        # Et on vérifie qu'il est bien égal à 3.
        self.assertEqual(count, 3)
        
        # On récupère l'identifiant de l'événement
        # concernant LLS1 pour plus tard.
        event = DBSession.query(Event.idevent
                        ).filter(Event.idsupitem == self.lls1.idsupitem 
                        ).one()
        idevent = event.idevent
        
        # On compte le nombre d'agrégats dans la table CorrEvent.
        aggregates = DBSession.query(CorrEvent
                    ).join((Event, Event.idevent == CorrEvent.idcause),)
        # Et on vérifie qu'il est bien égal à 2.
        self.assertEqual(2, aggregates.count())

        # On récupère les aggrégats en question.
        for aggregate in aggregates.all():
            # On vérifie que le nombre d'événements
            # qu'ils regroupent est bien 2.
            self.assertEqual(len(aggregate.events), 2)
            # On vérifie que l'événement concernant LLS1 en fait bien partie.
            self.assert_(idevent in [e.idevent for e in aggregate.events])
        
        # TODO: Corriger le problème avec les sessions
        DBSession.add(self.host)
        DBSession.add(self.lls1)

        # On recoit sur le bus un message "CRITICAL" concernant lls1.
        self.generate_message("CRITICAL", self.host.name, 
                                self.lls1.servicename)
        
        # TODO: Corriger le problème avec les sessions
        DBSession.add(self.lls1)
        
        # On compte le nombre d'événements dans la table Event.
        count = DBSession.query(Event).count()
        # Et on vérifie qu'il est bien égal à 3.
        self.assertEqual(count, 3)
        
        # On vérifie que l'événement concernant
        # LLS1 porte toujours le même identifiant.
        event = DBSession.query(Event.idevent
                        ).filter(Event.idsupitem == self.lls1.idsupitem 
                        ).one()
        self.assertEqual(idevent, event.idevent)
        
        # On compte le nombre d'agrégats dans la table CorrEvent.
        aggregates = DBSession.query(CorrEvent
                    ).join((Event, Event.idevent == CorrEvent.idcause),)
        # Et on vérifie qu'il est bien égal à 2.
        self.assertEqual(aggregates.count(), 2)
        
        # On récupère les aggrégats en question.
        for aggregate in aggregates.all():
            # On vérifie que le nombre d'événements
            # qu'ils regroupent est bien 2.
            self.assertEqual(len(aggregate.events), 2)
            # On vérifie que l'événement concernant LLS1 en fait bien partie.
            self.assert_(idevent in [e.idevent for e in aggregate.events])
        
        # TODO: Corriger le problème avec les sessions
        DBSession.add(self.host)
        DBSession.add(self.lls21)

        # On recoit sur le bus un message "CRITICAL" concernant lls21.
        self.generate_message("CRITICAL", self.host.name, 
                                self.lls21.servicename)
        
        # On compte le nombre d'événements dans la table Event.
        count = DBSession.query(Event).count()
        # Et on vérifie qu'il est bien égal à 4.
        self.assertEqual(count, 4)
        
        # TODO: Corriger le problème avec les sessions
        DBSession.add(self.lls21)
        
        # On récupère l'identifiant de l'événement concernant LLS21.
        event = DBSession.query(Event.idevent
                        ).filter(Event.idsupitem == self.lls21.idsupitem 
                        ).one()
        idevent = event.idevent
        
        # On compte le nombre d'agrégats dans la table CorrEvent.
        aggregates = DBSession.query(CorrEvent
                    ).join((Event, Event.idevent == CorrEvent.idcause),)
        # Et on vérifie qu'il n'y en a qu'un seul.
        self.assertEqual(aggregates.count(), 1)
        
        # On récupère l'aggrégat en question.
        aggregate = aggregates.one()
        # On vérifie qu'il regroupe exactement 4 événements.
        self.assertEqual(len(aggregate.events), 4)
        # On vérifie que l'événement concernant LLS21 en est bien la cause.
        self.assertEqual(idevent, aggregate.idcause)
    
       

