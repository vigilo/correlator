# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""
Module pour l'exécution d'une règle de corrélation
avec une limite sur la durée maximale d'exécution.
"""
import sys
import os
from twisted.protocols import amp
from ampoule import child

from vigilo.common.conf import settings
settings.load_module(__name__)

from vigilo.models.configure import configure_db
configure_db(settings['database'], 'sqlalchemy_')

from vigilo.common.conf import setup_plugins_path

from vigilo.common.logging import get_logger
from vigilo.common.gettext import translate

_ = translate(__name__)

class RuleCommand(amp.Command):
    arguments = [
        ('rule_name', amp.String()),
        ('idxmpp', amp.String()),
        ('xml', amp.Unicode()),
    ]
    response = [
    ]
    errors = {
        # Permet de capturer les erreurs les plus plausibles
        # pour pouvoir diagnostiquer facilement les problèmes.
        KeyError: 'KeyError',
        ValueError: 'ValueError',

        # Pour les autres erreurs, elles seront remontées
        # sous forme d'C{Exception}s génériques.
        Exception: 'Exception',
    }

class RuleRunner(child.AMPChild):
    def __init__(self, *args):
        sys.argv.insert(0, args[0])
        # Suppression du log sur la sortie standard (doublons)
        import twisted.python.log as twisted_logging
        for o in twisted_logging.theLogPublisher.observers[:]:
            if o.im_class == twisted_logging.FileLogObserver:
                twisted_logging.removeObserver(o)
        # Plugins
        setup_plugins_path(settings["correlator"].get("pluginsdir",
                           "/etc/vigilo/correlator/plugins"))
        super(RuleRunner, self).__init__()

    @RuleCommand.responder
    def rule_runner(self, rule_name, idxmpp, xml):
        from vigilo.correlator.registry import get_registry

        logger = get_logger(__name__)
        reg = get_registry()
        rule = reg.rules.lookup(rule_name)

        logger.debug(u'Rule runner: process begins for rule "%s"', rule_name)
        logger.debug(u'Process id: %(pid)r | Parent id: %(ppid)r | '
                      'Rule name: %(name)s', {
                            'pid': os.getpid(),
                            'ppid': os.getppid(),
                            'name': rule_name,
                        })

        try:
            rule.process(self, idxmpp, xml)
        except:
            logger.exception(_('Got an exception while running rule %(rule)s. '
                                'Running the correlator in the foreground '
                                '(%(prog)s -n) may help troubleshooting'), {
                                    'rule': rule_name,
                                    'prog': sys.argv[0],
                                })
            raise

        logger.debug(u'Rule runner: process ends for rule "%s"', rule_name)
        return {}
