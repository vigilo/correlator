# -*- coding: utf-8 -*-
from twisted.protocols import amp
from vigilo.correlator.amp.arguments import Function

class SendToBus(amp.Command):
    arguments = [
        ('item', amp.Unicode()),
    ]
    requiresAnswer = False

class RegisterCallback(amp.Command):
    arguments = [
        ('fn', Function()),
        ('idnt', amp.Unicode()),
    ]
    requiresAnswer = False
