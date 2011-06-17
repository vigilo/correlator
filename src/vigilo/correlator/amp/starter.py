# -*- coding: utf-8 -*-

from ampoule import main

class ProcessStarter(main.ProcessStarter):
    def __init__(self, rule_dispatcher, database, *args, **kwargs):
        self.rule_dispatcher = rule_dispatcher
        self.database = database
        super(ProcessStarter, self).__init__(*args, **kwargs)

    def startPythonProcess(self, prot, *args):
        prot.amp.rule_dispatcher = self.rule_dispatcher
        prot.amp.database = self.database
        return super(ProcessStarter, self).startPythonProcess(prot, *args)

