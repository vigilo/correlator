#!/usr/bin/env python

import os
import sys
import nose

testsdir = os.path.abspath(os.path.dirname(__file__))
topdir = os.path.abspath(os.path.join(testsdir, ".."))
os.chdir(topdir)

sys.path.insert(0, os.path.join(topdir, "lib"))

# Tests path
sys.argv.insert(1, "-w")
sys.argv.insert(2, testsdir)

# Run tests
nose.main()
