"""Ortho4XP Test Helpers
This script is a place to put constants and other functions that all tests can use, plus some setup.
"""

import os
import sys

TESTS_DIR = os.path.dirname(__file__)
TEMP_DIR = os.path.join(TESTS_DIR, 'tmp')
MOCKS_DIR = os.path.join(TESTS_DIR, 'mocks')

sys.path.insert(0, os.path.join(TESTS_DIR, '../src/'))
sys.path.insert(0, os.path.join(TESTS_DIR, '../Providers/'))

if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)


class MockSession:
    """
    For mocking image requests, this is more useful than the built-in mock module.
    It can even be used in conjunction with mocks and requests to return a fake session response.
    The primary reason this is needed is because of how sessions are currently passed between some functions.
    """
    def __init__(self):
        self.url = 'http://test.test'
        self.status_code = 500
        self.timeout = 1
        self.headers = {'Content-Type': 'image/jpeg', 'Content-Length': '0'}
        self.content = None

    def get(self, request_url, timeout=1, headers=None):
        """In order to return the proper session response"""
        if headers:
            self.headers = headers

        self.url = request_url
        self.timeout = timeout

        return self
