# This script is a place to put constants and other functions that all tests can use, plus some setup.

import os
import sys

TESTS_DIR = os.path.dirname(__file__)
TEMP_DIR = os.path.join(TESTS_DIR, 'tmp')
MOCKS_DIR = os.path.join(TESTS_DIR, 'mocks')

sys.path.insert(0, os.path.join(TESTS_DIR, '../src/'))
sys.path.insert(0, os.path.join(TESTS_DIR, '../Providers/'))

if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)
