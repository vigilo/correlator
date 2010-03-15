# -*- coding: utf-8 -*-
"""Suite de tests des logs du corrélateur"""

import unittest
import transaction

from datetime import datetime

from twisted.words.xish import domish

from utils import settings

from vigilo.correlator.xml import NS_EVENTS

from vigilo.correlator.context import Context

from vigilo.models.configure import DBSession
from vigilo.models import LowLevelService, Host, StateName, \
                            Dependency, Event, CorrEvent, Change

from utils import setup_mc, teardown_mc, setup_db, teardown_db

from vigilo.correlator.db_insertion import insert_event, insert_state

from vigilo.correlator.correvent import make_correvent

import logging
from vigilo.common.logging import get_logger
from vigilo.common.gettext import translate
LOGGER = get_logger(__name__)
_ = translate(__name__)


class RuleDispatcherStub():
    """Classe simulant le fonctionnement du RuleDispatcher."""
    
    def __init__(self, *args):
        """Initialisation."""
        self.buffer = []
        
    def sendItem(self, item):
        """Simule l'écriture d'un message sur la file"""
        self.buffer.append(item)
        
    def clear(self):
        """Vide la file de messages"""
        self.buffer = []


class test_log_handler(object):
    """Classe interceptant les logs du corrélateur pendant les tests."""
    
     # Attribut statique de classe
    instance = None
    
    def __new__(cls):
        """
        Constructeur
        
        @return: Une instance de la classe L{cls}.
        @rtype: L{cls}
        """
        if cls.instance is None:
            # Construction de l'objet..
            cls.instance = object.__new__(cls)
            # Initialisation de l'attribut contenant la connexion.
            cls.instance.buffer = []
        return cls.instance
        
    def write(self, message):
        """
        Écrit les messages dans le buffer.
        
        @param message: Le message à enregistrer.
        @type message: C{str}
        """
        LOGGER.debug("Ajout du message '%s' dans le syslog" % (message, ))
        self.buffer.append(message)
        
    def flush(self):
        """
        Simule la méthode flush des streams.
        """
        pass
        
    def clear(self):
        """
        Vide le buffer de messages.
        """
        self.buffer = []

syslog_handler = test_log_handler()
    
class TestLogging(unittest.TestCase):
    """
    Test de l'écriture des logs dans le corrélateur.
    
    Valide la satisfaction de l'exigence VIGILO_EXIG_VIGILO_COR_0040.
    """

    def simulate_message_reception(self,
        new_state, host_name, service_name=None):
        """
        Génère un message de changement d'état concernant l'item passé en 
        paramètre, réalise les mêmes traitements que ceux du rule_dispatcher
        et des règles, et déclenche l'exécution de la fonction make_correvent.
        """

        # On incrémente l'identifiant du message
        self.XMPP_id += 1
        
        # On génère un timestamp à partir de la date courante
        timestamp = datetime.now()
        
        # On génère le message xml qui devrait être
        # reçu sur le bus XMPP dans un tel cas. 
        item = domish.Element((NS_EVENTS, u'item'))
        event = item.addElement((NS_EVENTS, u'event'))
        # Ajout de l'attribut id
        item['id'] = str(self.XMPP_id)
        # Ajout de la balise timestamp
        tag = event.addElement(u'timestamp')
        tag.addContent(str(timestamp))
        # Ajout de la balise host
        tag = event.addElement(u'host')
        if host_name:
            tag.addContent(host_name)
        else:
            tag.addContent(settings['correlator']['nagios_hls_host'])
        # Ajout de la balise service
        tag = event.addElement(u'service')
        tag.addContent(service_name)
        # Ajout de la balise state
        tag = event.addElement(u'state')
        tag.addContent(new_state)
        # Ajout de la balise message
        tag = event.addElement(u'message')
        tag.addContent(new_state)
        # Conversion en XML
        payload = item.toXml()
        
        # On ajoute les données nécessaires dans le contexte.
        ctx = Context(self.XMPP_id)
        ctx.hostname = host_name
        ctx.servicename = service_name
        ctx.statename = new_state
        
        # On insère les données nécessaires dans la BDD:
        info_dictionary = {
            "host": host_name, 
            "service": service_name, 
            "state": new_state, 
            "timestamp": timestamp, 
            "message": new_state,}
        # - D'abord l'évènement ;
        ctx.raw_event_id = insert_event(info_dictionary)
        transaction.commit()
        transaction.begin()
        # - Et ensuite l'état.
        insert_state(info_dictionary)
        transaction.commit()
        transaction.begin()
        
        # On force le traitement du message, par la fonction make_correvent,
        # comme s'il avait été traité au préalable par le rule_dispatcher.
        rd = RuleDispatcherStub()
        make_correvent(rd, payload)
        transaction.commit()
        transaction.begin()

    def add_data(self):
        """
        Ajoute un hôte et un service de bas niveau dans la BDD, ainsi 
        que d'autres données nécessaires à l'exécution des tests.
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

        # Ajout d'un service de bas niveau dans la BDD.
        self.lls = LowLevelService(
            servicename = u'LLS',
            host = self.host,
            command = u'halt',
            op_dep = u'&',
            weight = 42,
        )
        
        transaction.commit()
        transaction.begin()
    
    def setUp(self):
        """Initialisation des tests"""
        
        # On prépare la base de données et le serveur MemcacheD.
        setup_mc()
        setup_db()

        # On récupère le logger 'vigilo.correlator.syslog'
        # défini dans les settings.
        self.logger = get_logger('vigilo.correlator.syslog')
        
        # On crée une instance de la classe test_log_handler()
        # pour intercepter les logs du corrélateur, et on
        # construit un StreamHandler à partir de cette instance.
        self.stream = test_log_handler()
        self.handler = logging.StreamHandler(self.stream)
        
        # On associe ce handler au logger.
        self.logger.addHandler(self.handler)
        
        # On crée un formatter (qui comme son nom l'indique permet de
        # spécifier le format des messages) qu'on associe lui-même au handler.
        formatter = logging.Formatter("%(message)s")
        self.handler.setFormatter(formatter)
        
        # Initialisation de l'identifiant des messages XML.
        self.XMPP_id = 0

    def tearDown(self):
        """Nettoie MemcacheD et la BDD à la fin de chaque test."""

        DBSession.flush()
        # Évite que d'anciennes instances viennent perturber le test suivant.
        DBSession.expunge_all()
        teardown_db()
        teardown_mc()
        
        # On dissocie le handler du logger.
        self.logger.removeHandler(self.handler)

    def test_log_new_event(self):
        """
        Syslog : nouvel évènement
        
        Vérifie que les logs générés lors de la création d'un nouvel
        évènement par le corrélateur sont conformes à ceux attendus.
        """
        
        # Insertion de données dans la base.
        self.add_data()
        
        DBSession.add(self.host)
        DBSession.add(self.lls)
        
        host_name = self.host.name
        
        lls_name = self.lls.servicename
        lls_id = self.lls.idservice
    
        # On recoit un message "WARNING" concernant lls1.
        LOGGER.debug(_("Réception d'un message 'WARNING' concernant lls1"))
        self.simulate_message_reception(u"WARNING", host_name, lls_name)
        
        event = DBSession.query(Event.idevent).one()
        event_id = event.idevent
        
        self.assertEqual(
            syslog_handler.buffer, [u'%(idevent)d|NEW|%(hostname)s|'
            '%(servicename)s|%(statename)s|%(priority)s|%(statename)s\n' % {
                'idevent': event_id,
                'hostname': host_name,
                'servicename': lls_name,
                'statename': u'WARNING',
                'priority': 4,
                }])

    def test_log_updated_event(self):
        """
        Syslog : mise à jour d'un évènement
        
        Vérifie que les logs générés lors de la mise à jour d'un
        évènement par le corrélateur sont conformes à ceux attendus.
        """
        
        # Insertion de données dans la base.
        self.add_data()
        
        DBSession.add(self.host)
        DBSession.add(self.lls)
        
        host_name = self.host.name
        
        lls_name = self.lls.servicename
        lls_id = self.lls.idservice
    
        # On recoit un message "WARNING" concernant lls1.
        LOGGER.debug(_("Réception d'un message 'WARNING' concernant lls1"))
        self.simulate_message_reception(u"WARNING", host_name, lls_name)
        
        event = DBSession.query(Event.idevent).one()
        event_id = event.idevent
        
        self.stream.clear()
    
        # On recoit un message "CRITICAL" concernant lls1.
        LOGGER.debug(_("Réception d'un message 'CRITICAL' concernant lls1"))
        ctx = Context(self.XMPP_id + 1)
        ctx.update_id = event_id
        self.simulate_message_reception(u"CRITICAL", host_name, lls_name)
        
        event = DBSession.query(Event.idevent).one()
        event_id = event.idevent
        
        self.assertEqual(
            syslog_handler.buffer, [u'%(idevent)d|CHANGE|%(hostname)s|'
            '%(servicename)s|%(statename)s|%(priority)s|%(statename)s\n' % {
                'idevent': event_id,
                'hostname': host_name,
                'servicename': lls_name,
                'statename': u'CRITICAL',
                'priority': 4,
                }])

