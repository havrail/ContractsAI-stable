import unittest
import sys
import os
import numpy as np
from PIL import Image

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.image_processing import ImageProcessor

class TestImageProcessor(unittest.TestCase):
    def test_preprocess_image(self):
        # Create a dummy image
        img = Image.new('RGB', (100, 100), color = 'white')
        processed = ImageProcessor.preprocess_image(img)
        self.assertIsInstance(processed, np.ndarray)
        self.assertEqual(processed.shape, (100, 100))

    def test_count_visual_signatures_empty(self):
        self.assertEqual(ImageProcessor.count_visual_signatures([]), 0)

if __name__ == '__main__':
    unittest.main()
