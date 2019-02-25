#!/usr/bin/env python3
#
# Just a simple script to run all tests from the command line.
#
import os
import unittest

loader = unittest.TestLoader()
start_dir = os.path.join(os.path.dirname(__file__))
suite = loader.discover(start_dir)

runner = unittest.TextTestRunner()
runner.run(suite)
