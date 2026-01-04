#!/usr/bin/env python3
"""
Frequency Analysis Module for Howdy
Detects screen moire patterns using FFT (Fast Fourier Transform) to prevent 2D spoofing attacks.
"""

import cv2
import numpy as np
from i18n import _

class FrequencyAnalyzer:
    def __init__(self, config=None):
        self.config = config
        # Threshold for detecting artificial patterns (high frequency anomalies)
        # Higher value = less sensitive, Lower value = more sensitive (more false positives)
        if config:
            self.moire_threshold = config.getfloat("security", "moire_threshold", fallback=0.15)
        else:
            self.moire_threshold = 0.15
            
        self.input_size = (128, 128) # Fixed size for FFT consistency

    def analyze(self, frame, face_location=None):
        """
        Analyze the frame (or face region) for moire patterns.
        Returns a score between 0.0 (natural) and 1.0 (artificial/screen).
        """
        try:
            # Crop to face if location provided
            if face_location:
                # Handle both dlib rect and tuple/list formats
                if hasattr(face_location, 'left'):
                    x, y, w, h = face_location.left(), face_location.top(), face_location.width(), face_location.height()
                else:
                    x, y, w, h = face_location
                    
                # Ensure crop is within bounds
                h_img, w_img = frame.shape[:2]
                x = max(0, x)
                y = max(0, y)
                w = min(w, w_img - x)
                h = min(h, h_img - y)
                
                if w <= 0 or h <= 0:
                    return 0.0
                    
                roi = frame[y:y+h, x:x+w]
            else:
                roi = frame

            # Convert to grayscale
            if len(roi.shape) == 3:
                gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            else:
                gray = roi

            # Resize for consistent FFT analysis
            gray_resized = cv2.resize(gray, self.input_size, interpolation=cv2.INTER_AREA)

            # Apply FFT
            f = np.fft.fft2(gray_resized)
            fshift = np.fft.fftshift(f)
            magnitude_spectrum = 20 * np.log(np.abs(fshift) + 1e-10)

            # Analyze high frequencies vs low frequencies
            # Moire patterns often show up as distinct spikes in high frequencies
            
            rows, cols = gray_resized.shape
            crow, ccol = rows // 2, cols // 2
            
            # Mask for center (low frequencies - natural features)
            mask_radius = 15
            mask = np.ones((rows, cols), np.uint8)
            cv2.circle(mask, (ccol, crow), mask_radius, 0, -1)
            
            # Extract high frequency components
            high_freq_magnitude = magnitude_spectrum * mask
            
            # Calculate energy stats
            mean_energy = np.mean(high_freq_magnitude)
            max_energy = np.max(high_freq_magnitude)
            
            # Heuristic: Artificial screens often have higher peak energy in high freqs
            # compared to natural skin texture.
            # Normalize score: simple heuristic based on max/mean ratio
            
            # Avoid division by zero
            if mean_energy == 0:
                return 0.0

            ratio = max_energy / (mean_energy + 1e-5)
            
            # Normalize to 0-1 range based on observed thresholds
            # Natural faces usually have lower ratios (smoother spectrum falloff)
            # Screens have higher ratios (spikes)
            
            # These constants might need tuning based on camera hardware
            base_ratio = 3.5 
            scale_factor = 2.0
            
            score = 1.0 / (1.0 + np.exp(-(ratio - base_ratio) * scale_factor))
            
            # Cap at 1.0
            return min(1.0, max(0.0, score))

        except Exception as e:
            print(f"Error in Frequency Analysis: {e}")
            return 0.0

    def is_spoof(self, score):
        """Returns True if score exceeds threshold"""
        return score > self.moire_threshold
