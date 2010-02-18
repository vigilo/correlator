# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""Configuration de la journalisation des événements issus de Twisted."""

from __future__ import absolute_import
import logging

from vigilo.correlator.libs import mp


def _check_logger_class():
    '''
    Make sure process name is recorded when loggers are used
    '''

    from multiprocessing.process import current_process
    logging._acquireLock()
    try:
        OldLoggerClass = logging.getLoggerClass()
        if not getattr(OldLoggerClass, '_process_aware', False):
            class ProcessAwareLogger(OldLoggerClass):
                _process_aware = True
                def makeRecord(self, *args, **kwds):
                    record = OldLoggerClass.makeRecord(self, *args, **kwds)
                    record.processName = current_process()._name
                    return record
            logging.setLoggerClass(ProcessAwareLogger)
    finally:
        logging._releaseLock()

def early_configure_logging():
    """
    Configure process-aware, twisted-aware logging.

    Limitations: if logging blocks, we block the twisted reactor.
    """

    # This has the side effect of changing the default logger class
    # to a LoggerAdapter-like that adds processName contextual info.
    # Must be called early, before this class is instanciated
    # in getLogger.
    # This has another side-effect of preparing the muliprocessing
    # atexit handlers.
    _check_logger_class()
    # Propagate from 'multiprocessing' to the parent (the root logger)
    mp.get_logger().propagate = True



def register(registry):
    """Méthode appelée pour activer la journalisation."""
    early_configure_logging()

