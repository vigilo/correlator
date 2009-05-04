#!/usr/bin/env python

import os
import sys
import nose

curdir = os.path.abspath(os.path.dirname(__file__))
os.chdir(os.path.join(curdir, ".."))

sys.path.insert(0, "lib")

nose.main(argv=["-w", "unittests"])
