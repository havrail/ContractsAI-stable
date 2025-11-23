import unittest
import sys
import os

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.utils import determine_telenity_entity

class TestUtils(unittest.TestCase):
    def test_determine_telenity_entity_known(self):
        code, full = determine_telenity_entity("Telenity FZE")
        self.assertEqual(code, "FzE - Telenity UAE")
        
    def test_determine_telenity_entity_unknown(self):
        code, full = determine_telenity_entity("Random Company")
        self.assertEqual(code, "Bilinmiyor")

    def test_determine_telenity_entity_fallback(self):
        code, full = determine_telenity_entity("Telenity Something")
        self.assertEqual(code, "TE - Telenity Europe")

if __name__ == '__main__':
    unittest.main()
