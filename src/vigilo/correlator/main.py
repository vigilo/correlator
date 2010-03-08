# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""
Module de lancement du corrélateur.
"""
from __future__ import absolute_import
import os

def main(*args):
    """Lancement avec Twistd"""
    import sys
    tac_file = os.path.join(os.path.dirname(__file__), "twisted_service.py")
    sys.argv[1:1] = ["-y", tac_file]
    from twisted.scripts.twistd import run
    run()

if __name__ == '__main__':
    main()

