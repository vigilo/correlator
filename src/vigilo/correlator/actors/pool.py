# -*- coding: utf-8 -*-

from vigilo.correlator.libs import mp
from multiprocessing.pool import Pool

class VigiloProcess(mp.Process):
    """Pool de processus du corrélateur"""
    def run(self):
        try:
            super(VigiloProcess, self).run()
        except KeyboardInterrupt:
            return

    def join(self, timeout=None):
        try:
            super(VigiloProcess, self).join(timeout)
        except KeyboardInterrupt:
            return

class VigiloPool(Pool):
    Process = VigiloProcess

