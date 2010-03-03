# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""
Module pour l'exécution d'une règle de corrélation
avec une limite sur la durée maximale d'exécution.
"""

from __future__ import absolute_import, with_statement

from contextlib import contextmanager
import signal
import os

from ..libs import etree

from ..registry import get_registry
from vigilo.correlator import rulesapi

from vigilo.common.logging import get_logger
from vigilo.common.gettext import translate

from vigilo.common.conf import settings

LOGGER = get_logger(__name__)
_ = translate(__name__)

api = None
def init(queue):
    """Initialisation globale."""
    global api
    if api is not None:
        raise RuntimeError
    api = rulesapi.Api(queue=queue)
    
class TimeoutError(Exception):
    """
    Exception levée lorsqu'une règle dépasse le temps d'exécution autorisé
    """
    pass

def sigalrm_handler(*args):
    """Routine pour le traitement du signal SIGALRM."""
    raise TimeoutError

@contextmanager
def deadline(seconds_to_deadline):
    """
    Context manager for running with a deadline.

    The deadline limits real execution time, even though it
    may have been spent outside of our process.
    This is apparently useless if the program is blocked in non-python code
    (pylibmc at least), even though we didn't install any handler.
    Kill it from outside then.

    Not reentrant, and this should be the sole user of alarm(2)
    (SIGALRM, signals.alarm) at the process level.

    Usage:
    >>> with deadline(3):
    ...     sleep(4)
    """

    if not isinstance(seconds_to_deadline, int):
        raise TypeError(seconds_to_deadline, int)
    if seconds_to_deadline < 1:
        raise ValueError(seconds_to_deadline, '< 1')

    old = signal.alarm(seconds_to_deadline)
    if old != 0:
        signal.alarm(old)
        raise RuntimeError

    try:
        yield
    finally:
        signal.alarm(0)


def process(args):
    """
    Lance l'exécution de la règle.
    
    @param args: Tuple contenant le nom de la règle et le code XML
        sur lequel elle va opérer.
    @type args: C{tuple} of (C{str}, C{str})
    """
    if api is None:
        raise RuntimeError

    (rule_name, xml) = args

    # If warranted, resource-limit rule process memory
    reg = get_registry()
    rule = reg.rules.lookup(rule_name)
    dom = etree.fromstring(xml)

    idnt = dom.get('id')
    # Only one payload below item or rfc violation.
    # Some implementations send the payload only on get requests
    if len(dom) != 1:
        raise RuntimeError
    payload = dom[0]
    
    LOGGER.debug(_(u'##### rule_runner: process begins #####'))
    LOGGER.debug(_(u'Process id: %(pid)r | Parent id: %(ppid)r | '
                   'Rule name: %(name)s') % {
                    'pid': os.getpid(),
                    'ppid': os.getppid(),
                    'name': rule_name,
                })
    
    signal.signal(signal.SIGALRM, sigalrm_handler)
    
    ex = None
    result = rulesapi.ETIMEOUT
    try:
        with deadline(settings['correlator'].as_int('rules_timeout')):
            result = rule.process(api, idnt, payload)
    except KeyboardInterrupt:
        import sys
        LOGGER.debug(_(u'##### KeyboardInterrupt #####'))
        sys.exit(0)
    except TimeoutError:
        LOGGER.error(_("The rule timed out (%r)") % rule_name)
        result = rulesapi.ETIMEOUT
    # @TODO Est-ce qu'on devrait capturer
    #   les exceptions de manière sélective ?
    except Exception, e:
        # On ne doit pas propager l'exception via "raise",
        # sans quoi on perdrait le groupe de processus.
        LOGGER.exception(_('while processing'))
        result = rulesapi.EEXCEPTION
        ex = e
    else:
        if result is None:
            LOGGER.info(_("The rule '%s' did not return any value, "
                    "assuming ENOERROR.") % rule_name)
            result = rulesapi.ENOERROR

    LOGGER.debug(_('##### rule_runner: process ends #####'))
    return (rule_name, result, ex)

