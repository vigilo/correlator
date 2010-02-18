#!/usr/bin/twistd -ny
# -*- coding: utf-8 -*-
# vim: set ft=python fileencoding=utf-8 sw=4 ts=4 et :
"""
A bit of glue, you can start this with twistd -ny path/to/file.py
"""

from twisted.application import service
from vigilo.correlator.pubsub import CorrServiceMaker

# XXX Est-ce que ce fichier est vraiment nécessaire/utile ???

# MAGIC: application is the convention twistd looks for.
application = service.Application('twisted/pubsub bits of the correlator')

# XXX manager devrait être initialisé correctement.
corr_service = CorrServiceMaker().makeService({'manager': None})
corr_service.setServiceParent(application)

