#!/usr/bin/env python

import os
import sys
import nose

testsdir = os.path.abspath(os.path.dirname(__file__))
topdir = os.path.abspath(os.path.join(testsdir, ".."))
os.chdir(topdir)

sys.path.append(topdir) # for settings.py

sys.argv[1:0] = [ '-v', '--with-doctest', '--cover-package=vigilo',
		'lib', 'unittests', ]

# Run tests
nose.main()
