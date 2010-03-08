# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""
Module pour l'exécution d'une règle de corrélation
avec une limite sur la durée maximale d'exécution.
"""
import os
from twisted.protocols import amp
from ampoule import child
from lxml import etree

from vigilo.common.conf import settings
settings.load_module(__name__)

from vigilo.models.configure import configure_db
configure_db(settings['database'], 'sqlalchemy_')

from vigilo.common.logging import get_logger
from vigilo.common.gettext import translate

LOGGER = get_logger(__name__)
_ = translate(__name__)

from vigilo.correlator.registry import get_registry
from vigilo.correlator import rulesapi

class RuleRunner(amp.Command):
    arguments = [
        ('rule_name', amp.String()),
        ('idxmpp', amp.String()),
        ('xml', amp.Unicode()),
    ]
    response = [
    ]
    errors = {
        Exception: 'Exception',
    }

class VigiloAMPChild(child.AMPChild):
    @RuleRunner.responder
    def rule_runner(self, rule_name, idxmpp, xml):
        reg = get_registry()
        rule = reg.rules.lookup(rule_name)

        LOGGER.debug(_('Rule runner: process begins for rule "%s"') %
            (rule_name, ))
        LOGGER.debug(_('Process id: %(pid)r | Parent id: %(ppid)r | '
                       'Rule name: %(name)s') % {
                        'pid': os.getpid(),
                        'ppid': os.getppid(),
                        'name': rule_name,
                    })

        rule.process(idxmpp, xml)
        LOGGER.debug(_('Rule runner: process ends for rule "%s"') %
            (rule_name, ))
        return {}

