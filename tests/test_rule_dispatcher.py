# -*- coding: utf-8 -*-
"""Teste le fonctionnement du rule dispatcher."""
import unittest
import transaction
import errno
from datetime import datetime

from twisted.words.xish import domish
from vigilo.corr.xml import NS_EVENTS

from vigilo.corr import rulesapi

from vigilo.models import HighLevelService, LowLevelService, Host, \
                            StateName, Dependency, Event, CorrEvent, Change
from vigilo.models.configure import DBSession

from vigilo.corr.connect import connect
from vigilo.corr.libs import mp
from vigilo.corr.actors.rule_dispatcher import handle_bus_message, \
                                                    handle_rules_errors, \
                                                    create_rule_runners_pool
from vigilo.corr.actors import rule_runner

from vigilo.corr.registry import Registry, get_registry
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
    timeout = 10

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
        
        # On lit le message sur le bus en utilisant la
        # fonction handle_bus_message du rule_dispatcher.
        self.rule_runners_pool = handle_bus_message(self.manager, 
            self.conn, None, self.rule_runners_pool)


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
        
        # Ajout de la date de dernière
        # modification de la topologie dans la BDD.
        DBSession.add(Change(
            element = u"Topology",
            last_modified = datetime.now(),))
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
        
        transaction.commit()
        transaction.begin()

    def setUp(self):
        """Initialise MemcacheD et la BDD au début de chaque test."""
        super(TestRuleDispatcher, self).setUp()
        setup_mc()
        setup_db()

        # Instanciation d'un manager.
        self.manager = mp.Manager()
        self.manager.in_queue = mp.Queue()
        self.manager.out_queue = mp.Queue()
        
        # Instanciation d'une connection à MemCacheD.
        self.conn = connect()
        
        # Enregistrement des règles à tester.
        self.register_rules()
        
        # Instanciation du pool de processus utilisé par le rule_dispatcher.
        self.rule_runners_pool = None
        
        # Lecture de la configuration pour déterminer
        # si l'on est en mode debugging ou non.
        try:
            self.debugging = settings['correlator'].as_bool('debugging')
        except KeyError:
            self.debugging = False

    def tearDown(self):
        """Nettoie MemcacheD et la BDD à la fin de chaque test."""
        super(TestRuleDispatcher, self).tearDown()
        DBSession.flush()
        # Évite que d'anciennes instances viennent perturber le test suivant.
        DBSession.expunge_all()
        teardown_db()
        teardown_mc()
        
        if self.rule_runners_pool:
            self.rule_runners_pool.close()
            notintr = False
            while not notintr:
                try:
                    self.rule_runners_pool.join()
                    notintr = True
                except OSError, ose:
                    if ose.errno != errno.EINTR:
                        raise ose
        
        from vigilo.corr.actors import rule_runner
        rule_runner.api = None

    def test_event_succession_1(self):
        """
        Traitement d'une succession d'événements bruts (1/2)
        
        LLS1 dépend de LLS11.
        
        On reçoit une première alerte sur LLS1.
        Puis une deuxième sur LLS11.
        Et enfin une nouvelle sur LLS1.
        """
        
        # Initialisation du pool de processus utilisé par le
        # rule_dispatcher, dans le cas où l'on utilise multiprocessing.
        if not self.debugging:
            # On crée un pool de processus qui 
            # sera utilisé par le rule_dispatcher.
            rule_runner.api = None
            self.rule_runners_pool = \
                create_rule_runners_pool(self.manager.out_queue)

        # Insertion de données dans la base.
        self.make_dependencies()
        
        DBSession.add(self.host)
        DBSession.add(self.lls1)
        DBSession.add(self.lls11)
        
        hostname = self.host.name
        
        lls1_name = self.lls1.servicename
        lls1_id = self.lls1.idservice
        
        lls11_name = self.lls11.servicename
        lls11_id = self.lls11.idservice
        
        # Initialisation de l'identifiant des messages du bus.
        self.idnt = 0

        # Au départ, la table Event doit être vide.
        events = DBSession.query(Event).all()
        self.assertEqual(events, [])
    
        # On recoit sur le bus un message "WARNING" concernant lls1.
        self.generate_message("WARNING", hostname, lls1_name)
        event = DBSession.query(Event.idevent).one()
        idevent = event.idevent
    
        # On recoit sur le bus un message "WARNING" concernant lls11.
        self.generate_message("WARNING", hostname, lls11_name)
        
        # On récupère l'identifiant de cet événement.
        lls11_event = DBSession.query(Event.idevent
                    ).filter(Event.idsupitem == lls11_id
                    ).one()
    
        # TODO: Corriger le problème avec les sessions
        DBSession.add(self.lls1)
        
        # On recoit sur le bus un message "CRITICAL" concernant lls1.
        self.generate_message("CRITICAL", hostname, lls1_name)
        
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
                    ).filter(Event.idsupitem == lls1_id
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
        Traitement d'une succession d'événements bruts (2/2)
        
        LLS1 dépend de LLS11 et de LLS12.
        LLS11 et LLS12 dépendent de LLS21.
        
        On reçoit une première alerte sur LLS11, et une deuxième sur LLS12.
        Ensuite, une alerte arrive concernant LLS1.
        Puis, on reçoit une nouvelle alerte sur LLS1.
        Enfin, une alerte arrive sur LLS21 
        """
        
        # Initialisation du pool de processus utilisé par le
        # rule_dispatcher, dans le cas où l'on utilise multiprocessing.
        if not self.debugging:
            # On crée un pool de processus qui 
            # sera utilisé par le rule_dispatcher.
            rule_runner.api = None
            self.rule_runners_pool = \
                create_rule_runners_pool(self.manager.out_queue)

        # Insertion de données dans la base.
        self.make_dependencies()
        
        DBSession.add(self.host)
        DBSession.add(self.lls1)
        DBSession.add(self.lls11)
        DBSession.add(self.lls12)
        DBSession.add(self.lls21)
        
        hostname = self.host.name
        
        lls1_name = self.lls1.servicename
        lls1_id = self.lls1.idservice
        
        lls11_name = self.lls11.servicename
        
        lls12_name = self.lls12.servicename
        
        lls21_name = self.lls21.servicename
        lls21_id = self.lls21.idservice
        
        # Initialisation de l'identifiant des messages du bus.
        self.idnt = 0

        # On recoit sur le bus un message "CRITICAL" concernant lls11.
        self.generate_message("CRITICAL", hostname, lls11_name)

        # On recoit sur le bus un message "CRITICAL" concernant lls12.
        self.generate_message("CRITICAL", hostname, lls12_name)

        # On recoit sur le bus un message "WARNING" concernant lls1.
        self.generate_message("WARNING", hostname, lls1_name)
        
        # On compte le nombre d'événements dans la table Event.
        count = DBSession.query(Event).count()
        # Et on vérifie qu'il est bien égal à 3.
        self.assertEqual(count, 3)
        
        # On récupère l'identifiant de l'événement
        # concernant LLS1 pour plus tard.
        event = DBSession.query(Event.idevent
                        ).filter(Event.idsupitem == lls1_id 
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

        # On recoit sur le bus un message "CRITICAL" concernant lls1.
        self.generate_message("CRITICAL", hostname, lls1_name)
        
        # On compte le nombre d'événements dans la table Event.
        count = DBSession.query(Event).count()
        # Et on vérifie qu'il est bien égal à 3.
        self.assertEqual(count, 3)
        
        # On vérifie que l'événement concernant
        # LLS1 porte toujours le même identifiant.
        event = DBSession.query(Event.idevent
                        ).filter(Event.idsupitem == lls1_id 
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

        # On recoit sur le bus un message "CRITICAL" concernant lls21.
        self.generate_message("CRITICAL", hostname, lls21_name)
        
        # On compte le nombre d'événements dans la table Event.
        count = DBSession.query(Event).count()
        # Et on vérifie qu'il est bien égal à 4.
        self.assertEqual(count, 4)
        
        # On récupère l'identifiant de l'événement concernant LLS21.
        event = DBSession.query(Event.idevent
                        ).filter(Event.idsupitem == lls21_id 
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

    def test_handle_rules_errors(self):
        """
        Traitement de règles qui échouent
        """
        # On instancie l'arbre des règles.
        rules_graph = Registry.global_instance().rules.step_rules
        
        # On initialise le pool de processus
        self.rule_runners_pool = None
        
        # On simule le traitement d'une règle qui fait un timeout.
        results = [("LowLevelServiceDepsRule", rulesapi.ETIMEOUT, None)]
        self.rule_runners_pool = handle_rules_errors(results, rules_graph, 
            self.manager.out_queue, self.rule_runners_pool)
        
        # On s'attend à ce que la fonction
        # handle_rules_errors ait recréé un pool de processus.
        self.assertTrue(isinstance(self.rule_runners_pool, mp.pool.Pool))
        
        # On s'attend à ce que la règle 'LowLevelServiceDepsRule'
        # ait été retiré de l'arbre des règles, ainsi que la 
        # règle 'UpdateOccurrencesCountRule' qui en dépend.
        rules = []
        for rule in rules_graph.rules:
            rules.append(rule)
        self.assertEqual(rules, [['HighLevelServiceDepsRule'], 
                                 ['UpdateAttributeRule', 'PriorityRule']])
        
        # On réinstancie l'arbre des règles.
        rules_graph = Registry.global_instance().rules.step_rules
        # On arrête le pool de processus et on le ré-initialise
        
        if self.rule_runners_pool:
            self.rule_runners_pool.close()
            notintr = False
            while not notintr:
                try:
                    self.rule_runners_pool.join()
                    notintr = True
                except OSError, ose:
                    if ose.errno != errno.EINTR:
                        raise ose
            self.rule_runners_pool = None
        
        # On simule le traitement d'une règle qui lève une exception.
        results = [("HighLevelServiceDepsRule", rulesapi.EEXCEPTION, None)]
        self.rule_runners_pool = handle_rules_errors(results, rules_graph, 
            self.manager.out_queue, self.rule_runners_pool)
        
        # On s'attend à ce que la fonction
        # handle_rules_errors ait recréé un pool de processus.
        self.assertTrue(isinstance(self.rule_runners_pool, mp.pool.Pool))
        
        # On s'attend à ce que la règle 'HighLevelServiceDepsRule'
        # ait été retiré de l'arbre des règles, ainsi que les règles 
        # 'UpdateAttributeRule' et 'PriorityRule' qui en dépendent.
        rules = []
        for rule in rules_graph.rules:
            rules.append(rule)
        self.assertEqual(rules, [['LowLevelServiceDepsRule'],
                                 ['UpdateOccurrencesCountRule']])
