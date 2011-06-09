# -*- coding: utf-8 -*-

from ampoule import main

class ProcessStarter(main.ProcessStarter):
    def __init__(self, rule_dispatcher, *args, **kwargs):
        self.rule_dispatcher = rule_dispatcher
        super(ProcessStarter, self).__init__(*args, **kwargs)

    def startPythonProcess(self, prot, *args):
        prot.amp.rule_dispatcher = self.rule_dispatcher
        return super(ProcessStarter, self).startPythonProcess(prot, *args)

