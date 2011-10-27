# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Module pour l'exécution d'une règle de corrélation
avec une limite sur la durée maximale d'exécution.
"""
from twisted.internet import defer
import transaction

from vigilo.common.logging import get_logger
from vigilo.common.gettext import translate
from vigilo.correlator.rule import ThreadWrapper

_ = translate(__name__)

class RuleRunner(object):
    def __init__(self, dispatcher, rule_name, rule_obj):
        self._name = rule_name
        self._rule = rule_obj
        self._rule.set_database(ThreadWrapper(dispatcher._database))
        self._dispatcher = ThreadWrapper(dispatcher)

    def run(self, idxmpp):
        logger = get_logger(__name__)
        logger.debug('Rule runner: process begins for rule "%s" (msgid=%r)',
                    self._name, idxmpp)

        def commit(res):
            transaction.commit()
            return res

        def abort(fail):
            logger.error(_('Got an exception while running rule ''"%(rule)s". '
                            'Running the correlator in the foreground '
                            '(service vigilo-correlator debug) may help '
                            'troubleshooting (%(error)s)'), {
                                'rule': self._name,
                                'error': fail.getErrorMessage(),
                            })
            transaction.abort()
            return fail

        def log_end(res):
            logger.debug('Rule runner: process ends for rule "%s"', self._name)
            return res

        transaction.begin()
        d = defer.maybeDeferred(
            self._rule.process,
            self._dispatcher,
            idxmpp)
        d.addCallback(commit)
        d.addErrback(abort)
        d.addBoth(log_end)
        return d
