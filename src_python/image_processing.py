import cv2
import numpy as np

class ImageProcessor:
    @staticmethod
    def preprocess_image(pil_image):
        # (Bu kısım aynı kalsın, değişiklik yok)
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
            
            # GÜNCELLEME: Footer (Sayfa No) Filtresi
            # Sayfanın alt %60'ından başla, ama en dipteki %10'u (footer) at.
            # Böylece sadece imza bloğunun olduğu yere odaklanırız.
            start_y = int(height * 0.60)
            end_y = int(height * 0.90) # En alt %10'luk kısmı atıyoruz
            
            roi = img[start_y:end_y, :] # Region of Interest
            
            gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
            # Threshold'u biraz artırıp gürültüyü azaltalım
            _, binary = cv2.threshold(gray, 140, 255, cv2.THRESH_BINARY_INV)
            
            ink_pixels = cv2.countNonZero(binary)
            total_pixels = binary.shape[0] * binary.shape[1]
            
            # Eşik değeri: %1.5 yerine %1.0 (alan daraldığı için)
            return (ink_pixels / total_pixels) > 0.01
        except Exception:
            return False

    # (Diğer metodlar aynı kalabilir)
    @staticmethod
    def count_visual_signatures(images):
        if not images: return 0
        count = 0
        for img in images:
            if ImageProcessor.detect_visual_signature(img):
                count += 1
        return count
