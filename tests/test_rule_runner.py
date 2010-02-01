# -*- coding: utf-8 -*-
"""
Test du rule_runner.
"""
import unittest
from time import sleep

from vigilo.corr.libs import mp

from vigilo.corr.rule import Rule

from vigilo.corr.actors import rule_runner
from vigilo.corr.registry import get_registry
from vigilo.corr.rulesapi import ENOERROR, ETIMEOUT, EEXCEPTION

from vigilo.common.logging import get_logger
from vigilo.common.gettext import translate

LOGGER = get_logger(__name__)
_ = translate(__name__)

from vigilo.common.conf import settings

class TimeoutRule(Rule):
    """ Règle conçue pour s'exécuter indéfiniment """

    def process(self, api, idnt, payload):
        """ Traitement du message par la règle. Ici une boucle infinie """
        LOGGER.critical(_("___Debut de l'execution de la regle de test___"))
#        sleep(settings['VIGILO_CORR_RULES_TIMEOUT'] + 30)
        while True:
            sleep(1)
        LOGGER.critical(_("___Fin de l'execution de la regle de test___"))
        return ENOERROR

def register(registry):
    """Enregistre la règle."""
    registry.rules.register(TimeoutRule())

class TestUpdateAttributeRule(unittest.TestCase):
    """ Classe de test du rule_runner """
    
    def test_rule_timeout(self):
        """
        Teste le code de retour de l'exécution d'une règle en cas de timeout.
        """
        
        registry = get_registry()
        registry.rules.clear()
        registry.rules.register(TimeoutRule())
        message = u"<item xmlns='http://jabber.org/protocol/pubsub'><aggr xmlns='http://www.projet-vigilo.org/xmlns/aggr1' id='foo'><superceded>423</superceded><superceded>523</superceded></aggr></item>"
        
        rule_runner.api = None
        out_queue = mp.Queue()
        rule_runner.init(out_queue)
        
        result = rule_runner.process(("TimeoutRule", message))
        
        self.assertEqual(result, ('TimeoutRule', ETIMEOUT))
        
        
        
        