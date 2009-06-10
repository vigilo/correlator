#!/usr/bin/env python

import os
import sys
import nose

testsdir = os.path.abspath(os.path.dirname(__file__))
topdir = os.path.abspath(os.path.join(testsdir, ".."))
os.chdir(topdir)

os.environ['VIGILO_SETTINGS_MODULE'] = 'settings_tests'
sys.path.append(topdir) # contains the settings module

sys.argv[1:0] = [ '-v',
		'--with-doctest',
		'--cover-package=vigilo',
		'--attr=!SEP',
		'lib', 'unittests', ]

# Run tests
nose.main()
