import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import Handler

class HostTests(unittest.TestCase):
    def test_foreign_host(self):
        handler = object.__new__(Handler)
        handler.headers = {'Host': 'attacker.example'}
        self.assertFalse(handler.allowed())
        handler.headers = {'Host': 'localhost:19133'}
        self.assertTrue(handler.allowed())
        handler.headers['Origin'] = 'https://attacker.example'
        self.assertFalse(handler.allowed())

    def test_configured_hosts_are_trimmed_and_lowercased(self):
        from unittest.mock import patch
        handler = object.__new__(Handler)
        handler.headers = {'Host': 'proxy.example', 'Origin': 'https://proxy.example'}
        with patch.dict('os.environ', {'AGENT_PAGES_ALLOWED_HOSTS': ' , PROXY.Example , '}):
            self.assertTrue(handler.allowed())
