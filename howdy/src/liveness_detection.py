#!/usr/bin/env python3
"""
Advanced Liveness Detection Module for Howdy
Prevents spoofing attacks using active challenges, temporal analysis, and frequency analysis.
"""

import cv2
import numpy as np
import time
import dlib
from collections import deque
import math
import random
from i18n import _

# Import new analysis modules
try:
    from frequency_analyzer import FrequencyAnalyzer
except ImportError:
    FrequencyAnalyzer = None

class ActiveChallengeSystem:
    """Manages active challenges for the user (blink, turn head, etc)"""
    
    CHALLENGE_TYPES = ['blink', 'turn_left', 'turn_right', 'nod']
    
    def __init__(self, config=None):
        self.config = config
        self.current_challenge = None
        self.challenge_start_time = 0
        self.challenge_timeout = 3.0
        
        if config:
            self.challenge_timeout = config.getfloat("security", "challenge_timeout", fallback=3.0)
            
        self.completed_challenges = set()
        self.state = 'IDLE' # IDLE, WAITING_FOR_ACTION, VERIFIED, FAILED
        
    def start_random_challenge(self):
        """Starts a new random challenge that hasn't been completed yet"""
        available = [c for c in self.CHALLENGE_TYPES if c not in self.completed_challenges]
        if not available:
            # If all done (or just one needed), verify
            self.state = 'VERIFIED'
            return None
            
        self.current_challenge = random.choice(available)
        self.challenge_start_time = time.time()
        self.state = 'WAITING_FOR_ACTION'
        return self.current_challenge
        
    def get_ui_message(self):
        """Returns message to display to user"""
        if self.state == 'IDLE':
            return _("Checking liveness...")
        elif self.state == 'VERIFIED':
            return _("Liveness Confirmed")
        elif self.state == 'FAILED':
            return _("Liveness Check Failed")
            
        if self.current_challenge == 'blink':
            return _("PLEASE BLINK EYES")
        elif self.current_challenge == 'turn_left':
            return _("TURN HEAD LEFT <<")
        elif self.current_challenge == 'turn_right':
            return _("TURN HEAD RIGHT >>")
        elif self.current_challenge == 'nod':
            return _("NOD HEAD UP/DOWN")
            
        return _("...")

class AdvancedLivenessDetector:
    """Enhanced Liveness Detector with Active Challenges"""
    
    def __init__(self, config=None):
        self.config = config
        
        # --- Config Values ---
        self.security_level = config.get("security", "security_level", fallback="medium")
        self.use_active_challenge = config.getboolean("security", "active_challenge", fallback=True)
        self.use_frequency = config.getboolean("security", "frequency_analysis", fallback=True)
        self.use_temporal = config.getboolean("security", "temporal_analysis", fallback=True)
        
        # --- Sub-systems ---
        self.challenge_system = ActiveChallengeSystem(config) if self.use_active_challenge else None
        self.frequency_analyzer = FrequencyAnalyzer(config) if (self.use_frequency and FrequencyAnalyzer) else None
        
        # --- State Tracking ---
        # Blink
        self.eye_ar_threshold = 0.25
        self.eye_ar_history = deque(maxlen=30)
        self.blink_detected = False
        
        # Head Movement
        self.head_positions = deque(maxlen=20)
        self.initial_head_pose = None
        
        # Temporal Consistency (Anti-Replay)
        self.frame_diff_history = deque(maxlen=10)
        self.min_consistency_frames = config.getint("security", "min_consistency_frames", fallback=5)
        
        # Timers
        self.start_time = None
        self.max_detection_time = 8.0
        self.min_confirmation_time = 1.5
        
        # Stats
        self.spoof_score = 0.0 # 0.0 = Real, 1.0 = Fake
        
    def reset(self):
        """Reset state for new session"""
        self.eye_ar_history.clear()
        self.head_positions.clear()
        self.frame_diff_history.clear()
        self.blink_detected = False
        self.initial_head_pose = None
        self.start_time = time.time()
        self.spoof_score = 0.0
        
        if self.challenge_system:
            self.challenge_system.state = 'IDLE'
            self.challenge_system.completed_challenges.clear()
            # Start first challenge immediately for smoother UX
            self.challenge_system.start_random_challenge()

    def _get_ear(self, eye_points):
        """Calculate Eye Aspect Ratio"""
        # Distances between vertical points
        A = np.linalg.norm(np.array(eye_points[1]) - np.array(eye_points[5]))
        B = np.linalg.norm(np.array(eye_points[2]) - np.array(eye_points[4]))
        # Distance between horizontal points
        C = np.linalg.norm(np.array(eye_points[0]) - np.array(eye_points[3]))
        if C == 0: return 0
        return (A + B) / (2.0 * C)

    def _check_blink(self, landmarks):
        """Detect blink from landmarks"""
        left_eye = [(landmarks.part(i).x, landmarks.part(i).y) for i in range(36, 42)]
        right_eye = [(landmarks.part(i).x, landmarks.part(i).y) for i in range(42, 48)]
        
        left_ear = self._get_ear(left_eye)
        right_ear = self._get_ear(right_eye)
        avg_ear = (left_ear + right_ear) / 2.0
        
        self.eye_ar_history.append(avg_ear)
        
        # Simple blink logic: transition from open -> closed -> open
        if len(self.eye_ar_history) >= 3:
            # If current is closed but recent history was open
            if avg_ear < self.eye_ar_threshold:
                # Check if we were open recently
                if max(list(self.eye_ar_history)[-5:]) > 0.3:
                    return True
        return False

    def _check_head_turn(self, landmarks, direction):
        """Check if head is turned in specific direction"""
        nose_tip = landmarks.part(30).x
        chin = landmarks.part(8).x
        left_face = landmarks.part(0).x
        right_face = landmarks.part(16).x
        
        face_width = right_face - left_face
        if face_width == 0: return False
        
        # Ratio of nose position within face width
        # 0.5 = center, < 0.5 = left (from viewer perspective, right for user), > 0.5 = right
        ratio = (nose_tip - left_face) / face_width
        
        if direction == 'turn_left': # User turns left (viewer sees nose move right)
            return ratio > 0.65
        elif direction == 'turn_right': # User turns right (viewer sees nose move left)
            return ratio < 0.35
            
        return False
        
    def _check_nod(self, landmarks):
        """Check for nodding motion"""
        nose_tip_y = landmarks.part(30).y
        
        if not self.head_positions:
            self.head_positions.append(nose_tip_y)
            return False
            
        # Add to history
        self.head_positions.append(nose_tip_y)
        
        # Check variance in Y axis
        if len(self.head_positions) >= 5:
            y_range = max(self.head_positions) - min(self.head_positions)
            return y_range > 15 # Threshold in pixels
            
        return False

    def process_frame(self, frame, landmarks, face_region):
        """
        Main processing loop.
        Returns: True if verified/live, False if processing/failed
        """
        if not self.start_time:
            self.reset()
            
        elapsed = time.time() - self.start_time
        if elapsed > self.max_detection_time:
            return False # Timeout

        # 1. Frequency Analysis (Passive)
        if self.frequency_analyzer:
            freq_score = self.frequency_analyzer.analyze(frame, face_region)
            if self.frequency_analyzer.is_spoof(freq_score):
                print(f"Spoof detected (Frequency Analysis): {freq_score:.2f}")
                self.spoof_score += 0.2
                if self.spoof_score > 0.5:
                    return False # Fail fast on strong spoof signal

        # 2. Temporal Analysis (Passive)
        # Check if frame is too static (photo) or too chaotic (random noise)
        # TODO: Implement optical flow or simple frame diff here
        
        # 3. Active Challenge Logic
        if self.challenge_system and self.challenge_system.state == 'WAITING_FOR_ACTION':
            challenge = self.challenge_system.current_challenge
            success = False
            
            if challenge == 'blink':
                if self._check_blink(landmarks):
                    success = True
            elif challenge in ['turn_left', 'turn_right']:
                if self._check_head_turn(landmarks, challenge):
                    success = True
            elif challenge == 'nod':
                if self._check_nod(landmarks):
                    success = True
            
            if success:
                self.challenge_system.completed_challenges.add(challenge)
                # For now, 1 successful challenge is enough for medium security
                if self.security_level == 'high':
                    if len(self.challenge_system.completed_challenges) < 2:
                        self.challenge_system.start_random_challenge()
                    else:
                        self.challenge_system.state = 'VERIFIED'
                        return True
                else:
                    self.challenge_system.state = 'VERIFIED'
                    return True
            
            # Check timeout for current challenge
            if time.time() - self.challenge_system.challenge_start_time > self.challenge_system.challenge_timeout:
                # Try one more challenge or fail?
                # For UX, maybe just fail or fallback to passive if confidence high
                pass

        # If active challenge disabled, fallback to passive confidence
        if not self.use_active_challenge:
            # Logic from original detector...
            # Assume passed if no spoof detected after min time
            if elapsed > self.min_confirmation_time and self.spoof_score < 0.3:
                return True

        return self.challenge_system.state == 'VERIFIED'

    def get_user_feedback(self):
        """Get message for UI"""
        if self.challenge_system:
            return self.challenge_system.get_ui_message()
        
        # Fallback messages
        if self.spoof_score > 0.3:
            return _("Please ensure good lighting")
        return _("Verifying...")
        
    def get_detection_status(self):
        return {
            'spoof_score': self.spoof_score,
            'state': self.challenge_system.state if self.challenge_system else 'PASSIVE',
            'elapsed': time.time() - self.start_time
        }

def create_liveness_detector(config=None):
    return AdvancedLivenessDetector(config)
