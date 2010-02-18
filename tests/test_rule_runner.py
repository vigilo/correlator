# -*- coding: utf-8 -*-
"""
Test du rule_runner.
"""
import unittest
from time import sleep

from vigilo.correlator.libs import mp

from vigilo.correlator.rule import Rule

from vigilo.correlator.actors import rule_runner
from vigilo.correlator.registry import get_registry
from vigilo.correlator.rulesapi import ENOERROR, ETIMEOUT, EEXCEPTION

from vigilo.common.logging import get_logger
from vigilo.common.gettext import translate

LOGGER = get_logger(__name__)
_ = translate(__name__)

class TimeoutRule(Rule):
    """ Règle conçue pour s'exécuter indéfiniment """

    def process(self, api, idnt, payload):
        """ Traitement du message par la règle. Ici une boucle infinie """
        while True:
            sleep(1)
        return ENOERROR

class ExceptionRule(Rule):
    """ Règle conçue pour lever une exception """

    def process(self, api, idnt, payload):
        """ Traitement du message par la règle. Ici on lève une exception """
        raise ValueError, "Exception"
        return ENOERROR

class TestUpdateAttributeRule(unittest.TestCase):
    """ Classe de test du rule_runner """
    
    def test_rule_timeout(self):
        """Code de retour d'une règle en cas de timeout"""
        
        registry = get_registry()
        registry.rules.clear()
        registry.rules.register(TimeoutRule())
        message = u"<item xmlns='http://jabber.org/protocol/pubsub'><aggr xmlns='http://www.projet-vigilo.org/xmlns/aggr1' id='foo'><superceded>423</superceded><superceded>523</superceded></aggr></item>"
        
        rule_runner.api = None
        out_queue = mp.Queue()
        rule_runner.init(out_queue)
        
        result = rule_runner.process(("TimeoutRule", message))
        
        self.assertEqual(result, ('TimeoutRule', ETIMEOUT, None))
    
    def test_rule_exception(self):
        """Code de retour d'une règle en cas d'exception"""
        
        registry = get_registry()
        registry.rules.clear()
        registry.rules.register(ExceptionRule())
        message = u"<item xmlns='http://jabber.org/protocol/pubsub'><aggr xmlns='http://www.projet-vigilo.org/xmlns/aggr1' id='foo'><superceded>423</superceded><superceded>523</superceded></aggr></item>"
        
        rule_runner.api = None
        out_queue = mp.Queue()
        rule_runner.init(out_queue)
        
        result = rule_runner.process(("ExceptionRule", message))
        
        self.assertEqual(result[0], 'ExceptionRule')
        self.assertEqual(result[1], EEXCEPTION)
        self.assertTrue(result[2])
        self.assertTrue(isinstance(result[2], ValueError))
        self.assertEqual(str(result[2]), 'Exception')
        
        
        
        
