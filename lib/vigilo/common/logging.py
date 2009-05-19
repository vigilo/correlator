# vim: set fileencoding=utf-8 sw=4 ts=4 et :
from __future__ import absolute_import

"""
Sets up logging, with twisted and multiprocessing integration.
"""

import logging

# slight layering issue, move libs to common?
from vigilo.corr.libs import mp
import twisted.python.log as twisted_logging

__all__ = ( 'get_logger', )

tw_obs = None
def get_logger(name):
    """
    Gets a logger from a dotted name.

    Ensures early, basic initialisation is done.
    This must replace all uses of logging.getLogger.

    Since name should be the package name, a common use pattern is:
        LOGGER = get_logger(__name__)

    Limitations: if logging blocks, we block the twisted reactor.
    """

    global tw_obs
    if tw_obs is None:
        # This has the side effect of changing the default logger class
        # to a LoggerAdapter-like that adds processName contextual info.
        # Must be called early, before this class is instanciated
        # in getLogger.
        # This has another side-effect of preparing the muliprocessing
        # atexit handlers.
        mp.get_logger()
        # Propagate from 'multiprocessing' to the parent (the root logger)
        mp.get_logger().propagate = True
        # The blocking issue could be addressed by not logging to stderr,
        # or not directly (a queue could do). Ctrl-S (XOFF) blocks.
        tw_obs = twisted_logging.PythonLoggingObserver()
        tw_obs.start()
    return logging.getLogger(name)

