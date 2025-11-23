import cv2
import numpy as np

class ImageProcessor:
    @staticmethod
    def preprocess_image(pil_image):
        """OCR öncesi gürültü azaltma ve kontrast iyileştirme."""
        img = np.array(pil_image)
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
        gray = cv2.medianBlur(gray, 3)
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )
        denoised = cv2.fastNlMeansDenoising(binary, None, 30, 7, 21)
        return denoised

    @staticmethod
    def detect_visual_signature(pil_image):
        try:
            img = np.array(pil_image)
            height, width, _ = img.shape
            bottom_third = img[int(height * 0.66):, :]
            gray = cv2.cvtColor(bottom_third, cv2.COLOR_RGB2GRAY)
            _, binary = cv2.threshold(gray, 120, 255, cv2.THRESH_BINARY_INV)
            ink_pixels = cv2.countNonZero(binary)
            total_pixels = binary.shape[0] * binary.shape[1]
            return (ink_pixels / total_pixels) > 0.015
        except Exception:
            return False

    @staticmethod
    def count_visual_signatures(images):
        """Tüm sayfaların alt üçte birinde imza var mı sayar."""
        if not images:
            return 0
        count = 0
        for img in images:
            if ImageProcessor.detect_visual_signature(img):
                count += 1
        return count
