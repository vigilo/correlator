# -*- coding: utf-8 -*-
"""
Test du rule_runner.
"""
#import unittest
from twisted.trial import unittest
from time import sleep
from cStringIO import StringIO

#from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, Deferred
from twisted.internet.error import ProcessTerminated
from twisted.internet import reactor
# On réutilise les mécanismes d'ampoule.
from ampoule.test.test_process import FakeAMP, _FakeT
from ampoule import main, pool

from vigilo.correlator.rule import Rule

from vigilo.correlator.actors.rule_dispatcher import RuleDispatcher
from vigilo.correlator.registry import get_registry

from vigilo.common.logging import get_logger

from vigilo.correlator.actors.rule_runner import VigiloAMPChild, RuleRunner

LOGGER = get_logger('vigilo.correlator.tests')

class SpecificException(Exception):
    message = "Oops!"
    def __init__(self):
        super(SpecificException, self).__init__(self.message)

class ExceptionRuleRunner(RuleRunner):
    pass

class ExceptionAMPChild(VigiloAMPChild):
    @ExceptionRuleRunner.responder
    def rule_runner(self, *args, **kwargs):
        raise SpecificException()

class TimeoutRuleRunner(RuleRunner):
    pass

class TimeoutAMPChild(VigiloAMPChild):
    @TimeoutRuleRunner.responder
    def rule_runner(self, *args, **kwargs):
        from time import sleep
        sleep(999)

class TestRuleException(unittest.TestCase):
    """ Classe de test du comportement du rule dispatcher en cas d'erreurs."""
    def setUp(self):
        super(TestRuleException, self).setUp()

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
            timeout=2,
            name='ExceptionRuleDispatcher',
            min=1, max=1,
        )
        yield pp.start()

        def _fail():
            self.fail("Expected an exception!")

        def _checks(failure):
            try:
                failure.raiseException()
            except Exception, e:
                self.assertEquals(e.message, SpecificException.message)
            else:
                _fail()

        work = pp.doWork(
            ExceptionRuleRunner,
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
        )
        yield pp.start()

        def _fail():
            self.fail("Expected an exception!")

        def _checks(failure):
            self.assertTrue(failure.check(ProcessTerminated),
                "Incorrect exception")

        work = pp.doWork(
            TimeoutRuleRunner,
            rule_name='Timeout',
            idxmpp='foo',
            xml='foo',
        )
        work.addCallbacks(lambda *args: _fail, _checks)
        yield work
        yield pp.stop()

