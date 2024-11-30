import vehicle_api
import time
import pytesseract
from PIL import Image
import pyscreenshot as ImageGrab
from fuzzywuzzy import fuzz
import cv2
import numpy as np

pytesseract.pytesseract.tesseract_cmd = 'C:\\Program Files\\Tesseract-OCR\\tesseract.exe'

# Configuration
MATCH_THRESHOLD = 90  # Fuzzy match threshold (0-100)
CHECK_INTERVAL = 1.0  # Seconds between checks
REGION = (3400, 160, 3840, 230)  # Top-right 960px wide by 200px tall


class VehicleOcr():
    def __init__(self):
        self.vehicleApi = vehicle_api.VehicleApi()
        self.vehicle_names = self.vehicleApi.get_all_vehicle_names()

    def main(self):
        print("Starting OCR and fuzzy match script...")
        while True:
            self.show_overlay(REGION)  # Display the overlay
            matches = self.perform_ocr_and_match(REGION, self.vehicle_names, MATCH_THRESHOLD)
            if matches:
                print(f"Matches found: {matches}")
                pass
            else:
                print("No matches found.")
            time.sleep(CHECK_INTERVAL)

    def perform_ocr_and_match(self, region, target_words, threshold):
        # Take a screenshot of the specified region
        screenshot = ImageGrab.grab(bbox=region)
        
        # Perform OCR
        text = pytesseract.image_to_string(screenshot, lang="eng")
        detected_words = [x for x in text.strip().lower().split(' ') if len(x) > 2]

        
        # Fuzzy match
        matches = []
        for word in target_words:
            for detected in detected_words:
                if word and detected:
                    score = fuzz.partial_ratio(detected.lower(), word.lower())
                    if score >= threshold:
                        matches.append((word, score))
        
        return matches

    def show_overlay(self, region):
        """Display an overlay with the OCR region."""
        # Take a screenshot of the full screen
        screenshot = ImageGrab.grab()
        screen_np = np.array(screenshot)  # Convert screenshot to a NumPy array
        screen_np = cv2.cvtColor(screen_np, cv2.COLOR_RGB2BGR)  # Convert RGB to BGR for OpenCV

        # Draw the rectangle on the screenshot
        x1, y1, x2, y2 = region
        color = (0, 255, 0)  # Green rectangle
        thickness = 2
        cv2.rectangle(screen_np, (x1, y1), (x2, y2), color, thickness)

        # Display the overlay
        cv2.imshow("OCR Overlay", screen_np)

        # Allow interruption to close the overlay window
        if cv2.waitKey(1) & 0xFF == ord('q'):
            cv2.destroyAllWindows()
            exit()


if __name__ == '__main__':
    VehicleOcr().main()
