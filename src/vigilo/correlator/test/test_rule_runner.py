# -*- coding: utf-8 -*-
"""
Test du rule_runner.
"""

import os
import sys
from time import sleep
from cStringIO import StringIO

# ATTENTION: contrairement aux autres modules, ici il faut utiliser
# twisted.trial, sinon ça ne marche pas (ça dérange AMPoule). Attention à bien
# vérifier que les échecs ne sont pas interceptés par nose.
from twisted.trial import unittest
from twisted.internet import reactor
#import unittest
#from nose.twistedtools import reactor, deferred

from twisted.internet.defer import inlineCallbacks, Deferred
from twisted.internet.error import ProcessTerminated
# On réutilise les mécanismes d'ampoule.
from ampoule.test.test_process import FakeAMP, _FakeT
from ampoule import main, pool

from utils import settings

from vigilo.correlator.rule import Rule

from vigilo.correlator.actors.rule_dispatcher import RuleDispatcher
from vigilo.correlator.registry import get_registry

from vigilo.common.logging import get_logger

from vigilo.correlator.actors.rule_runner import RuleCommand, RuleRunner

LOGGER = get_logger('vigilo.correlator.tests')

class SpecificException(Exception):
    msg = "Oops!"
    def __init__(self):
        super(SpecificException, self).__init__(self.msg)

class ExceptionRuleCommand(RuleCommand):
    pass

class ExceptionAMPChild(RuleRunner):
    @ExceptionRuleCommand.responder
    def rule_runner(self, *args, **kwargs):
        raise SpecificException()

class TimeoutRuleCommand(RuleCommand):
    pass

class TimeoutAMPChild(RuleRunner):
    @TimeoutRuleCommand.responder
    def rule_runner(self, *args, **kwargs):
        from time import sleep
        sleep(999)

class TestRuleException(unittest.TestCase):
    """ Classe de test du comportement du rule dispatcher en cas d'erreurs."""

    def setUp(self):
        super(TestRuleException, self).setUp()

        # Permet de gérer l'environnement créé par Buildout
        self.starter = main.ProcessStarter(env={
                    "PYTHONPATH": ":".join(sys.path),
                    "VIGILO_SETTINGS": os.environ["VIGILO_SETTINGS"],
                    })

        # Permet d'attendre le lancement du reactor
        # avant de continuer l'exécution des tests.
        d = Deferred()
        reactor.callLater(0, d.callback, None)
        return d

    @inlineCallbacks
    def test_rule_exception(self):
        """Test d'une règle qui lève une exception."""
        pp = pool.ProcessPool(
            ampChild=ExceptionAMPChild,
            timeout=10,
            name='ExceptionRuleDispatcher',
            min=1, max=1,
            starter=self.starter,
            ampChildArgs=("dummy"),
        )
        yield pp.start()

        def _fail():
            self.fail("Expected an exception!")

        def _checks(failure):
            try:
                failure.raiseException()
            except Exception, e:
                self.assertEquals(str(e), SpecificException.msg)
            else:
                _fail()

        work = pp.doWork(
            ExceptionRuleCommand,
            rule_name='Exception',
            idxmpp='bar',
            xml='bar',
        )
        work.addCallbacks(lambda *args: _fail, _checks)
        yield work
        yield pp.stop()

    @inlineCallbacks
    def test_rule_timeout(self):
        """Test d'une règle qui dépasse le délai maximum autorisé."""
        pp = pool.ProcessPool(
            ampChild=TimeoutAMPChild,
            timeout=2,
            name='TimeoutRuleDispatcher',
            min=1, max=1,
            starter=self.starter,
            ampChildArgs=("dummy"),
        )
        yield pp.start()

        def _fail(r):
            self.fail("Expected an exception!")

        def _checks(failure):
            self.assertTrue(failure.check(ProcessTerminated),
                "Incorrect exception")
            self.assertEqual(failure.value.signal, 9,
                "Le process s'est arrêté de la mauvaise façon")

        work = pp.doWork(
            TimeoutRuleCommand,
            rule_name='Timeout',
            idxmpp='foo',
            xml='foo',
        )
        work.addCallbacks(_fail, _checks)
        yield work
        yield pp.stop()
