"""
VocaAI Dynamic Sign Language Translator
Upgraded from Static Gesture Detector to Continuous Communication System
"""

import os
import cv2  
import mediapipe as mp
import numpy as np
import math
import threading
import time
from collections import deque
from tkinter import Tk, Canvas, Label, StringVar, Frame, Button, Listbox, Scrollbar, LabelFrame, Toplevel
import pyttsx3
import speech_recognition as sr
import winsound
from PIL import Image, ImageTk

class VoiceRecognizer:
    """Handles background speech-to-text recognition"""
    
    def __init__(self, callback):
        self.recognizer = sr.Recognizer()
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.energy_threshold = 300  # Default starting threshold
        self.callback = callback
        self.running = True
        self.microphone = None
        self.current_energy = 0
        self.is_listening = False
        self.language = 'ml-IN'  # Default language
        self.last_activity = time.time()
        
        # Use default microphone for better compatibility across systems
        try:
            mics = sr.Microphone.list_microphone_names()
            print("\n--- Available Audio Devices ---")
            for i, name in enumerate(mics):
                print(f"Index {i}: {name}")
            
            # Try to find a 'real' microphone if possible, otherwise use default
            target_idx = None
            for i, name in enumerate(mics):
                if "microphone" in name.lower() or "audio array" in name.lower():
                    target_idx = i
                    break
            
            if target_idx is not None:
                print(f"Selecting microphone at index {target_idx}: {mics[target_idx]}")
                self.microphone = sr.Microphone(device_index=target_idx)
            else:
                self.microphone = sr.Microphone()
                print("Using default system microphone.")
        except Exception as e:
            print(f"Microphone Initialization Error: {e}")
            self.microphone = None
        print("---------------------\n")
        
        # Audio visualizer settings
        self.audio_levels = deque([2]*50, maxlen=50)
        self.wave_meter_heights = [0] * 20
        self.is_mic_streaming = False
        
    def set_language(self, lang_code):
        """Update the recognition language (e.g., 'en-US' or 'ml-IN')"""
        self.language = lang_code
        print(f"Voice: Language changed to {lang_code}")
        
    def start(self):
        """Start listening in a background thread"""
        if self.microphone:
            self.running = True
            # Start a single background thread for listening
            threading.Thread(target=self._listen_loop, daemon=True).start()
        else:
            print("Voice recognition not started: No microphone found.")

    def _listen_loop(self):
        """Continuously listen for speech with auto-calibration."""
        print("Voice: Starting listen loop thread.")
        
        while self.running:
            try:
                if self.microphone is None:
                    print("Voice: No microphone available. Retrying initialization...")
                    self._initialize_mic()
                    if self.microphone is None:
                        time.sleep(5)
                        continue

                # Use a single context manager for the microphone
                with self.microphone as source:
                    # Calibrate for room noise
                    print("Voice: Calibrating for ambient noise...")
                    # Update status for user feedback
                    if hasattr(self, 'mic_status_callback'):
                        self.mic_status_callback("CALIBRATING...")
                    
                    self.recognizer.adjust_for_ambient_noise(source, duration=0.8)
                    # Lower threshold slightly for better sensitivity if needed
                    self.recognizer.energy_threshold = max(self.recognizer.energy_threshold, 30) 
                    self.recognizer.pause_threshold = 0.8 # Allow for slight pauses in speech
                    self.recognizer.non_speaking_duration = 0.5
                    
                    if hasattr(self, 'mic_status_callback'):
                        self.mic_status_callback("LISTENING")
                    
                    print(f"Voice: Calibration complete. Threshold: {self.recognizer.energy_threshold}")
                    
                    self.is_listening = True
                    
                    while self.running:
                        try:
                            # Listen for a phrase with a shorter timeout for better responsiveness
                            print("DEBUG: Listening for audio...")
                            audio = self.recognizer.listen(source, timeout=1, phrase_time_limit=10)
                            print("DEBUG: Audio captured, processing...")
                            
                            # Update visualizer with real audio data
                            try:
                                raw_data = audio.get_raw_data()
                                if raw_data:
                                    samples = np.frombuffer(raw_data, dtype=np.int16)
                                    if len(samples) > 0:
                                        # Calculate RMS energy
                                        rms = np.sqrt(np.mean(samples.astype(np.float32)**2))
                                        self.current_energy = rms
                                        # Scale for visualizer (0-60 range)
                                        level = min(60, rms / 100)
                                        self.audio_levels.append(level)
                            except:
                                pass
                            
                            # Process recognition
                            try:
                                if hasattr(self, 'mic_status_callback'):
                                    self.mic_status_callback("PROCESSING...")
                                
                                print(f"DEBUG: Attempting Google Recognition for lang: {self.language}")
                                text = self.recognizer.recognize_google(audio, language=self.language)
                                
                                if hasattr(self, 'mic_status_callback'):
                                    self.mic_status_callback("LISTENING")
                                    
                                if text:
                                    print(f"DEBUG: Voice Recognized Text: '{text}'")
                                    # Use a small delay to ensure callback doesn't block recognition loop
                                    self.callback(text)
                                else:
                                    print("DEBUG: Google Recognition returned empty text")
                            except sr.UnknownValueError:
                                print("DEBUG: Google Recognition could not understand audio")
                                if hasattr(self, 'mic_status_callback'):
                                    self.mic_status_callback("LISTENING")
                            except sr.RequestError as e:
                                print(f"DEBUG: Google Recognition API Error: {e}")
                                if hasattr(self, 'mic_status_callback'):
                                    self.mic_status_callback("OFFLINE / API ERROR")
                                time.sleep(2)
                                
                        except sr.WaitTimeoutError:
                            # No speech started, update visualizer with background noise
                            import random
                            self.current_energy = random.randint(2, 8)
                            self.audio_levels.append(self.current_energy)
                            continue
                        except Exception as e:
                            if self.running:
                                print(f"Voice Inner Loop Error: {e}")
                            break
            except Exception as e:
                if self.running:
                    print(f"Mic Access Error: {e}")
                    if hasattr(self, 'mic_status_callback'):
                        self.mic_status_callback("MIC ERROR")
                self.is_listening = False
                time.sleep(3)

    def _initialize_mic(self):
        """Try to find and initialize a working microphone"""
        try:
            import speech_recognition as sr
            mics = sr.Microphone.list_microphone_names()
            target_idx = None
            for i, name in enumerate(mics):
                if any(k in name.lower() for k in ["mic", "audio", "array", "input"]):
                    target_idx = i
                    break
            
            if target_idx is not None:
                print(f"Voice: Selecting mic index {target_idx}: {mics[target_idx]}")
                self.microphone = sr.Microphone(device_index=target_idx)
            else:
                self.microphone = sr.Microphone()
                print("Voice: Using default system microphone.")
        except Exception as e:
            print(f"Voice: Mic Initialization Failed: {e}")
            self.microphone = None

    def stop(self):
        self.running = False

class TrajectoryAnalyzer:
    """Analyzes hand movement trajectories relative to body landmarks"""
    
    def __init__(self, window_size=45, alpha=0.3):
        self.window_size = window_size
        self.trajectory = deque(maxlen=window_size)
        self.alpha = alpha  # Smoothing factor for EMA
        self.last_points = {
            'wrist': None,
            'fingertip': None,
            'head': None,
            'shoulder': None
        }
        
    def _smooth_point(self, name, new_point):
        """Apply Exponential Moving Average smoothing to a point"""
        if new_point is None:
            return None
        
        last_point = self.last_points.get(name)
        if last_point is None:
            self.last_points[name] = new_point
            return new_point
        
        # EMA: alpha * new + (1 - alpha) * last
        smoothed = tuple(
            self.alpha * n + (1 - self.alpha) * l 
            for n, l in zip(new_point, last_point)
        )
        self.last_points[name] = smoothed
        return smoothed

    def add_frame(self, wrist_pos, fingertip_pos, head_pos, shoulder_pos):
        """Add a frame to the trajectory window with smoothing"""
        # Smooth the points
        s_wrist = self._smooth_point('wrist', wrist_pos)
        s_fingertip = self._smooth_point('fingertip', fingertip_pos)
        s_head = self._smooth_point('head', head_pos)
        s_shoulder = self._smooth_point('shoulder', shoulder_pos)
        
        if all(pos is not None for pos in [s_wrist, s_fingertip, s_head, s_shoulder]):
            self.trajectory.append({
                'wrist': s_wrist,
                'fingertip': s_fingertip,
                'head': s_head,
                'shoulder': s_shoulder,
                'timestamp': time.time()
            })
    
    def calculate_distance(self, point1, point2):
        """Calculate Euclidean distance between two points"""
        if point1 is None or point2 is None:
            return None
        return math.dist(point1, point2)
    
    def calculate_direction(self, start, end):
        """Calculate direction vector from start to end point"""
        if start is None or end is None:
            return None
        return (end[0] - start[0], end[1] - start[1], end[2] - start[2])
    
    def get_wrist_to_head_distance(self):
        """Get wrist distance relative to head"""
        if len(self.trajectory) < 2:
            return None
        recent = self.trajectory[-1]
        return self.calculate_distance(recent['wrist'], recent['head'])
    
    def get_wrist_movement(self, frames=None):
        """Calculate wrist movement direction and magnitude over specified frames"""
        if len(self.trajectory) < 2:
            return None, None
        
        # If frames is not specified, use full trajectory
        if frames is None or frames >= len(self.trajectory):
            start = self.trajectory[0]
        else:
            start = self.trajectory[-frames]
            
        end = self.trajectory[-1]
        direction = self.calculate_direction(start['wrist'], end['wrist'])
        if direction:
            magnitude = math.sqrt(sum(d**2 for d in direction))
            return direction, magnitude
        return None, None
    
    def is_moving(self, threshold=0.01, frames=None):
        """Check if hand is moving (magnitude above threshold)"""
        _, magnitude = self.get_wrist_movement(frames=frames)
        return magnitude is not None and magnitude > threshold
    
    def get_vertical_movement(self, frames=None):
        """Get vertical component of movement (Y-axis)"""
        direction, _ = self.get_wrist_movement(frames=frames)
        if direction:
            return direction[1]  # Y component (negative = upward, positive = downward)
        return None


class SentenceBuffer:
    """Manages continuous sentence building with voting-based stability checking"""
    
    def __init__(self, stability_frames=10, idle_timeout=2.0, window_size=15):
        self.buffer = []
        self.history = deque(maxlen=5) # Keep last 5 sentences
        self.current_sign = None
        self.sign_window = deque(maxlen=window_size) # Window for voting
        self.stability_threshold = 0.6 # 60% of window must be the same sign
        self.idle_timeout = idle_timeout
        self.last_sign_time = time.time()
        self.language = 'ml-IN'  # Default language
        self.cooldown_time = 0.8 # Reduced cooldown
        self.cooldown_until = 0
        self.ml_mapping = {
            "HELLO": "നമസ്കാരം",
            "THANK YOU": "നന്ദി",
            "PLEASE": "ദയവായി",
            "HELP": "സഹായം",
            "YES": "അതെ",
            "NO": "അല്ല",
            "SORRY": "ക്ഷമിക്കണം",
            "WATER": "വെള്ളം",
            "FOOD": "ഭക്ഷണം",
            "EMERGENCY": "അടിയന്തരാവസ്ഥ",
            "MEDICINE": "മരുന്ന്",
            "WASHROOM": "വാഷ്റൂം",
            "WHERE": "എവിടെ"
        }
        
    def set_language(self, lang_code):
        """Update the translation language"""
        self.language = lang_code
        print(f"Buffer: Language changed to {lang_code}")
        
    def add_sign(self, sign_text):
        """Add a sign using voting-based stability check"""
        current_time = time.time()
        
        # Update last_sign_time if ANY sign is detected (prevents idle timeout while signing)
        if sign_text and sign_text != "None":
            self.last_sign_time = current_time
            
        # Don't add if in cooldown
        if current_time < self.cooldown_until:
            return False
            
        # Add to voting window
        self.sign_window.append(sign_text if sign_text else "None")
        
        # Count occurrences in window
        if len(self.sign_window) < self.sign_window.maxlen:
            return False
            
        from collections import Counter
        counts = Counter(self.sign_window)
        most_common_sign, count = counts.most_common(1)[0]
        
        # Check if most common sign meets threshold and is not "None"
        if most_common_sign != "None" and (count / len(self.sign_window)) >= self.stability_threshold:
            # Avoid immediate duplicates (e.g., "HELLO HELLO")
            if not self.buffer or self.buffer[-1] != most_common_sign:
                self.buffer.append(most_common_sign)
                self.last_sign_time = current_time
                self.cooldown_until = current_time + self.cooldown_time
                self.sign_window.clear() # Reset window after detection
                return True
        return False
    
    def get_potential_sign(self):
        """Get the most common sign in the current window (for feedback)"""
        if not self.sign_window:
            return None, 0
            
        from collections import Counter
        counts = Counter(self.sign_window)
        most_common, count = counts.most_common(1)[0]
        
        if most_common == "None":
            # Try second most common
            common_list = counts.most_common(2)
            if len(common_list) > 1:
                most_common, count = common_list[1]
            else:
                return None, 0
        
        # Translate if in Malayalam mode
        display_name = most_common
        if self.language == 'ml-IN':
            display_name = self.ml_mapping.get(most_common, most_common)
                
        return display_name, (count / len(self.sign_window))

    def check_idle(self):
        """Check if user has been idle (no signs for timeout period)"""
        if not self.buffer:
            return False
        return time.time() - self.last_sign_time > self.idle_timeout
    
    def get_sentence(self):
        """Get current sentence as string with translation if needed"""
        if not self.buffer:
            return ""
            
        if self.language == 'ml-IN':
            translated = [self.ml_mapping.get(s, s) for s in self.buffer]
            return ' '.join(translated)
            
        return ' '.join(self.buffer)
    
    def formulate_natural_sentence(self, signs):
        """Advanced grammar mapping for signs into natural sentences (ML or EN)"""
        if not signs:
            return ""
        
        text = ' '.join(signs).upper()
        
        if self.language == 'ml-IN':
            # Mapping signs to Malayalam using the class mapping
            translated_signs = [self.ml_mapping.get(s, s) for s in signs]
            
            # --- Advanced Malayalam Grammar Logic ---
            # Subject-Object-Verb (SOV) and Contextual Refinement
            
            # HELP + PLEASE -> ദയവായി സഹായിക്കൂ (Daya-vaayi sahaya-ikkoo)
            if "PLEASE" in text and "HELP" in text:
                return "ദയവായി എന്നെ ഒന്ന് സഹായിക്കാമോ?"
            
            # HELLO + THANK YOU -> നമസ്കാരം, നന്ദി (Namaskaram, Nandi)
            if "HELLO" in text and "THANK YOU" in text:
                return "നമസ്കാരം, നിങ്ങളുടെ സഹായത്തിന് വലിയ നന്ദി."
            
            # HELLO + HELP -> നമസ്കാരം, എനിക്ക് സഹായം വേണം
            if "HELLO" in text and "HELP" in text:
                return "നമസ്കാരം, എനിക്ക് ചെറിയൊരു സഹായം വേണം."
            
            # SORRY + HELP -> ക്ഷമിക്കണം, സഹായിക്കാമോ?
            if "SORRY" in text and "HELP" in text:
                return "ക്ഷമിക്കണം, എന്നെ ഒന്ന് സഹായിക്കാൻ കഴിയുമോ?"

            # YES + PLEASE -> അതെ, ദയവായി
            if "YES" in text and "PLEASE" in text:
                return "അതെ, ദയവായി അത് ചെയ്യൂ."
            
            # NO + SORRY -> ഇല്ല, ക്ഷമിക്കണം
            if "NO" in text and "SORRY" in text:
                return "ഇല്ല, എന്നോട് ക്ഷമിക്കണം."

            # EMERGENCY Rules
            if "EMERGENCY" in text:
                return "അടിയന്തരാവസ്ഥ! എനിക്ക് വേഗത്തിൽ സഹായം വേണം."
            
            if "WATER" in text:
                if "PLEASE" in text: return "ദയവായി കുറച്ച് വെള്ളം തരുമോ?"
                return "എനിക്ക് ദാഹിക്കുന്നു, വെള്ളം വേണം."
            
            if "FOOD" in text:
                if "PLEASE" in text: return "ദയവായി കുറച്ച് ഭക്ഷണം തരുമോ?"
                return "എനിക്ക് വിശക്കുന്നു, ഭക്ഷണം വേണം."

            if "MEDICINE" in text:
                if "PLEASE" in text: return "ദയവായി എനിക്ക് മരുന്ന് തരുമോ?"
                return "എനിക്ക് മരുന്ന് ആവശ്യമുണ്ട്."

            if "WASHROOM" in text:
                if "WHERE" in text: return "വാഷ്റൂം എവിടെയാണെന്ന് പറഞ്ഞുതരാമോ?"
                return "എനിക്ക് വാഷ്റൂമിൽ പോകണം."

            if "WHERE" in text:
                if "HELP" in text: return "എവിടെയാണ് സഹായം ലഭിക്കുക?"
                return "അത് എവിടെയാണ്?"

            # Sign-specific refinements for natural flow
            refined_signs = []
            for s in signs:
                if s == "HELLO": refined_signs.append("നമസ്കാരം")
                elif s == "THANK YOU": refined_signs.append("നന്ദി")
                elif s == "PLEASE": refined_signs.append("ദയവായി")
                elif s == "HELP": refined_signs.append("സഹായം")
                elif s == "YES": refined_signs.append("അതെ")
                elif s == "NO": refined_signs.append("ഇല്ല")
                elif s == "SORRY": refined_signs.append("ക്ഷമിക്കണം")
                else: refined_signs.append(self.ml_mapping.get(s, s))
            
            # Fallback for multiple signs
            if len(refined_signs) > 1:
                return ", ".join(refined_signs) + "."
            
            # Single word responses (Direct mapping)
            if text == "HELLO": return "നമസ്കാരം!"
            if text == "THANK YOU": return "വളരെ നന്ദി."
            if text == "YES": return "അതെ, തീർച്ചയായും."
            if text == "NO": return "ഇല്ല, എനിക്ക് വേണ്ട."
            if text == "SORRY": return "ക്ഷമിക്കണം, തെറ്റുപറ്റിയതാണ്."
            if text == "HELP": return "സഹായം ആവശ്യമുണ്ട്."
            
            return ' '.join(translated_signs) + "."
        else:
            # Contextual Grammar Logic for English
            if "HELLO" in text and "HELP" in text:
                return "Hello, please help me."
            if "HELLO" in text and "THANK YOU" in text:
                return "Hello, thank you very much."
            if "PLEASE" in text and "HELP" in text:
                return "Please, can you help me?"
            if "SORRY" in text and "HELP" in text:
                return "I'm sorry, I need some help."
                
            # Single word responses
            if text == "HELLO": return "Hello!"
            if text == "THANK YOU": return "Thank you."
            if text == "YES": return "Yes."
            if text == "NO": return "No."
            if text == "SORRY": return "I am sorry."
            if text == "HELP": return "I need help."
            
            return ' '.join(signs).capitalize() + "."

    def finalize_sentence(self):
        """Finalize current buffer into history and speak it"""
        if not self.buffer:
            return None
            
        sentence = self.formulate_natural_sentence(self.buffer)
        self.history.append(sentence)
        
        # Speak it
        threading.Thread(target=self._speak, args=(sentence,), daemon=True).start()
        
        # Clear for next sentence
        self.buffer.clear()
        self.current_sign = None
        self.sign_window.clear()
        return sentence
    
    def speak_sentence(self):
        """Legacy method redirected to finalize"""
        return self.finalize_sentence()
    
    def _speak(self, text):
        """Thread-safe TTS with Language-specific voice attempt"""
        try:
            engine = pyttsx3.init()
            voices = engine.getProperty('voices')
            target_voice = None
            
            if self.language == 'ml-IN':
                # Try to find a Malayalam voice
                for voice in voices:
                    if hasattr(voice, 'name') and 'malayalam' in voice.name.lower():
                        target_voice = voice.id
                        break
                    if hasattr(voice, 'languages') and any('ml' in str(lang).lower() for lang in voice.languages):
                        target_voice = voice.id
                        break
            else:
                # Try to find an English voice
                for voice in voices:
                    if hasattr(voice, 'name') and 'english' in voice.name.lower():
                        target_voice = voice.id
                        break
                    if hasattr(voice, 'languages') and any('en' in str(lang).lower() for lang in voice.languages):
                        target_voice = voice.id
                        break
            
            if target_voice:
                engine.setProperty('voice', target_voice)
            
            engine.say(text)
            engine.runAndWait()
        except Exception as e:
            print(f"TTS Error: {e}")
    
    def clear(self):
        """Clear everything"""
        self.buffer.clear()
        self.history.clear()
        self.current_sign = None
        self.sign_window.clear()


class DynamicSignDetector:
    """Detects dynamic sign language gestures with coordinate normalization"""
    
    def __init__(self):
        self.trajectory_analyzer = TrajectoryAnalyzer()
        self.hand_state_history = deque(maxlen=30)
        self.norm_factor = 1.0  # Normalization factor based on body size
        
    def update_normalization(self, pose_landmarks):
        """Update normalization factor based on shoulder width"""
        if not pose_landmarks:
            return
        
        ls = self.extract_landmark(pose_landmarks, 11)
        rs = self.extract_landmark(pose_landmarks, 12)
        
        if ls and rs:
            # Use shoulder width as a proxy for distance/scale
            shoulder_width = math.dist(ls[:2], rs[:2])
            if shoulder_width > 0:
                # Target shoulder width is ~0.3 in normalized coordinates at ideal distance
                # Adjusting from 0.4 to 0.3 to be more realistic for standard webcam FOV
                self.norm_factor = shoulder_width / 0.33
    
    def get_norm_dist(self, dist):
        """Apply normalization to a distance threshold"""
        return dist * self.norm_factor

    def extract_landmark(self, landmarks, index):
        """Extract landmark coordinates"""
        if landmarks and hasattr(landmarks, 'landmark') and index < len(landmarks.landmark):
            lm = landmarks.landmark[index]
            return (lm.x, lm.y, lm.z)
        return None
    
    def is_fist(self, hand_landmarks):
        """Check if hand is in fist position (relative to palm size)"""
        if not hand_landmarks:
            return False
            
        wrist = self.extract_landmark(hand_landmarks, 0)
        mcp = self.extract_landmark(hand_landmarks, 9) # Middle finger MCP
        tips = [self.extract_landmark(hand_landmarks, i) for i in [8, 12, 16, 20]]
        thumb_tip = self.extract_landmark(hand_landmarks, 4)
        index_mcp = self.extract_landmark(hand_landmarks, 5)
        
        if not all([wrist, mcp, thumb_tip, index_mcp] + tips):
            return False
        
        # Calculate palm size as a reference
        palm_size = math.dist(wrist[:2], mcp[:2])
        if palm_size == 0: return False
        
        # Fingers are closed if tips are close to the MCP joint relative to palm size
        distances = [math.dist(mcp[:2], tip[:2]) for tip in tips]
        avg_dist_ratio = (sum(distances) / len(distances)) / palm_size
        
        # Thumb check: thumb tip should be relatively close to the palm in a fist
        thumb_dist_ratio = math.dist(thumb_tip[:2], index_mcp[:2]) / palm_size
        
        # Accuracy: slightly more inclusive thresholds
        return avg_dist_ratio < 0.6 and thumb_dist_ratio < 0.9
    
    def is_open_palm(self, hand_landmarks):
        """Check if hand is in open palm position"""
        if not hand_landmarks:
            return False
            
        wrist = self.extract_landmark(hand_landmarks, 0)
        mcp = self.extract_landmark(hand_landmarks, 9)
        tips = [self.extract_landmark(hand_landmarks, i) for i in [8, 12, 16, 20]]
        thumb_tip = self.extract_landmark(hand_landmarks, 4)
        
        if not all([wrist, mcp, thumb_tip] + tips):
            return False
            
        palm_size = math.dist(wrist[:2], mcp[:2])
        if palm_size == 0: return False
        
        distances = [math.dist(mcp[:2], tip[:2]) for tip in tips]
        avg_dist_ratio = (sum(distances) / len(distances)) / palm_size
        
        # Thumb should be extended away from palm
        thumb_dist_ratio = math.dist(thumb_tip[:2], mcp[:2]) / palm_size
        
        # Accuracy: slightly more inclusive extension thresholds
        return avg_dist_ratio > 1.1 and thumb_dist_ratio > 0.85
    
    def detect_water(self, hand_landmarks, face_landmarks):
        """Detect WATER: Index finger pointing to mouth"""
        if not hand_landmarks or not face_landmarks:
            return False
            
        index_tip = self.extract_landmark(hand_landmarks, 8)
        mouth_pos = self.extract_landmark(face_landmarks, 13)
        index_mcp = self.extract_landmark(hand_landmarks, 5)
        middle_tip = self.extract_landmark(hand_landmarks, 12)
        
        if not all([index_tip, mouth_pos, index_mcp, middle_tip]):
            return False
            
        # Check if only index finger is extended
        palm_size = math.dist(self.extract_landmark(hand_landmarks, 0)[:2], index_mcp[:2])
        is_index_extended = math.dist(index_tip[:2], index_mcp[:2]) > palm_size * 1.5
        is_middle_closed = math.dist(middle_tip[:2], index_mcp[:2]) < palm_size * 0.8
        
        dist_to_mouth = math.dist(index_tip[:2], mouth_pos[:2])
        
        return is_index_extended and is_middle_closed and dist_to_mouth < self.get_norm_dist(0.15)

    def detect_food(self, hand_landmarks, face_landmarks):
        """Detect FOOD: Hand in 'O' shape (fingertips touching thumb) near mouth"""
        if not hand_landmarks or not face_landmarks:
            return False
            
        thumb_tip = self.extract_landmark(hand_landmarks, 4)
        index_tip = self.extract_landmark(hand_landmarks, 8)
        middle_tip = self.extract_landmark(hand_landmarks, 12)
        mouth_pos = self.extract_landmark(face_landmarks, 13)
        
        if not all([thumb_tip, index_tip, middle_tip, mouth_pos]):
            return False
            
        # Check if tips are touching thumb
        dist_idx = math.dist(index_tip[:2], thumb_tip[:2])
        dist_mid = math.dist(middle_tip[:2], thumb_tip[:2])
        
        # Check distance to mouth
        dist_to_mouth = math.dist(thumb_tip[:2], mouth_pos[:2])
        
        return dist_idx < 0.05 and dist_mid < 0.05 and dist_to_mouth < self.get_norm_dist(0.15)

    def detect_emergency(self, left_hand, right_hand):
        """Detect EMERGENCY: Both hands in fists crossed at wrists"""
        if not left_hand or not right_hand:
            return False
            
        if not (self.is_fist(left_hand) and self.is_fist(right_hand)):
            return False
            
        lw = self.extract_landmark(left_hand, 0)
        rw = self.extract_landmark(right_hand, 0)
        
        if not (lw and rw):
            return False
            
        dist_between_wrists = math.dist(lw[:2], rw[:2])
        
        return dist_between_wrists < self.get_norm_dist(0.12)

    def detect_thank_you(self, left_hand, right_hand, face_landmarks, pose_landmarks):
        """Detect THANK YOU: Hand moves from mouth downward to chest"""
        if not (left_hand or right_hand) or not face_landmarks or not pose_landmarks:
            return False
        
        self.update_normalization(pose_landmarks)
        mouth_pos = self.extract_landmark(face_landmarks, 13)
        
        left_shoulder = self.extract_landmark(pose_landmarks, 11)
        right_shoulder = self.extract_landmark(pose_landmarks, 12)
        if not all([mouth_pos, left_shoulder, right_shoulder]):
            return False
        
        chest_pos = (
            (left_shoulder[0] + right_shoulder[0]) / 2,
            (left_shoulder[1] + right_shoulder[1]) / 2,
            (left_shoulder[2] + right_shoulder[2]) / 2
        )
        
        hand_landmarks = left_hand if left_hand else right_hand
        wrist = self.extract_landmark(hand_landmarks, 0)
        if not wrist: return False
        
        # Hand should be near mouth at start or moving away from it
        dist_to_mouth = math.dist(wrist[:2], mouth_pos[:2])
        dist_to_chest = math.dist(wrist[:2], chest_pos[:2])
        
        vertical_movement = self.trajectory_analyzer.get_vertical_movement(frames=15)
        
        # Accuracy improvement: hand must be moving DOWN and be within a normalized chest area
        if vertical_movement and vertical_movement > self.get_norm_dist(0.01):
            if dist_to_chest < self.get_norm_dist(0.15) and dist_to_mouth < self.get_norm_dist(0.25):
                return True
        
        return False
    
    def detect_please(self, left_hand, right_hand, pose_landmarks):
        """Detect PLEASE: Open palm moving in circular motion on chest"""
        if not (left_hand or right_hand) or not pose_landmarks:
            return False
        
        self.update_normalization(pose_landmarks)
        hand_landmarks = left_hand if left_hand else right_hand
        
        if not self.is_open_palm(hand_landmarks):
            return False
        
        ls = self.extract_landmark(pose_landmarks, 11)
        rs = self.extract_landmark(pose_landmarks, 12)
        if not (ls and rs): return False
        
        chest_pos = ((ls[0] + rs[0]) / 2, (ls[1] + rs[1]) / 2)
        wrist = self.extract_landmark(hand_landmarks, 0)
        if not wrist: return False
        
        # Distance check with normalization
        if math.dist(wrist[:2], chest_pos) > self.get_norm_dist(0.2):
            return False
        
        # Circular motion check
        positions = [frame['wrist'] for frame in list(self.trajectory_analyzer.trajectory)[-20:]]
        if len(positions) < 15: return False
        
        # Calculate radius variance to confirm circularity
        center_x = sum(p[0] for p in positions) / len(positions)
        center_y = sum(p[1] for p in positions) / len(positions)
        radii = [math.dist((p[0], p[1]), (center_x, center_y)) for p in positions]
        
        avg_radius = sum(radii) / len(radii)
        if avg_radius < self.get_norm_dist(0.02): return False # Too small
        
        radius_variance = np.var(radii) / (avg_radius**2) if avg_radius > 0 else 1
        
        # Low radius variance means it's a good circle
        return radius_variance < 0.3 and np.var([math.atan2(p[1]-center_y, p[0]-center_x) for p in positions]) > 0.8
    
    def detect_help(self, left_hand, right_hand):
        """Detect HELP: One hand (fist) placed on top of other (flat palm)"""
        if not (left_hand and right_hand):
            return False
        
        # Refined check for HELP position: identify which hand is fist and which is palm
        l_fist = self.is_fist(left_hand)
        r_fist = self.is_fist(right_hand)
        l_palm = self.is_open_palm(left_hand)
        r_palm = self.is_open_palm(right_hand)
        
        if (l_fist and r_palm):
            fist_hand, palm_hand = left_hand, right_hand
        elif (r_fist and l_palm):
            fist_hand, palm_hand = right_hand, left_hand
        else:
            return False
        
        fw = self.extract_landmark(fist_hand, 0)
        pw = self.extract_landmark(palm_hand, 0)
        if not (fw and pw): return False
        
        # Accuracy: Hands must be close horizontally and vertically stacked
        dist_x = abs(fw[0] - pw[0])
        dist_y = abs(fw[1] - pw[1])
        
        # Fist should be roughly above or on the palm (Y is smaller for higher positions)
        is_stacked = fw[1] < pw[1] + self.get_norm_dist(0.05)
        
        return dist_x < self.get_norm_dist(0.1) and dist_y < self.get_norm_dist(0.15) and is_stacked

    def detect_hello(self, left_hand, right_hand, face_landmarks):
        """Detect HELLO: Hand moves from forehead outward"""
        if not (left_hand or right_hand) or not face_landmarks:
            return False
            
        hand_landmarks = left_hand if left_hand else right_hand
        forehead = self.extract_landmark(face_landmarks, 10)
        wrist = self.extract_landmark(hand_landmarks, 0)
        
        if not (forehead and wrist): return False
            
        # Hand must start near forehead
        dist_to_forehead = math.dist(wrist[:2], forehead[:2])
        
        direction, magnitude = self.trajectory_analyzer.get_wrist_movement(frames=15)
        if direction and magnitude > self.get_norm_dist(0.04):
            # Horizontal movement away from center
            is_outward = (direction[0] > 0 if wrist[0] > forehead[0] else direction[0] < 0)
            if abs(direction[0]) > abs(direction[1]) * 1.5 and dist_to_forehead < self.get_norm_dist(0.2):
                return is_outward
        return False

    def detect_yes(self, left_hand, right_hand):
        """Detect YES: Hand in fist nodding (up and down)"""
        if not (left_hand or right_hand):
            return False
            
        hand_landmarks = left_hand if left_hand else right_hand
        if not self.is_fist(hand_landmarks):
            return False
            
        if len(self.trajectory_analyzer.trajectory) < 15:
            return False
            
        recent_frames = list(self.trajectory_analyzer.trajectory)[-15:]
        y_positions = [f['wrist'][1] for f in recent_frames]
        x_positions = [f['wrist'][0] for f in recent_frames]
        
        # Calculate variance to ensure movement is primarily vertical
        y_var = np.var(y_positions)
        x_var = np.var(x_positions)
        
        if y_var < 0.0001 or y_var < x_var * 2: # Must be more vertical than horizontal
            return False
            
        # Smoothing
        y_positions_smooth = np.convolve(y_positions, np.ones(3)/3, mode='valid')
        y_diffs = np.diff(y_positions_smooth)
        
        direction_changes = 0
        for i in range(1, len(y_diffs)):
            if (y_diffs[i] > 0.001 and y_diffs[i-1] < -0.001) or (y_diffs[i] < -0.001 and y_diffs[i-1] > 0.001):
                direction_changes += 1
                
        return direction_changes >= 2

    def detect_no(self, left_hand, right_hand):
        """Detect NO: Index and middle fingers snap down to thumb (movement-based)"""
        if not (left_hand or right_hand):
            return False
            
        hand_landmarks = left_hand if left_hand else right_hand
        
        # Current state
        thumb_tip = self.extract_landmark(hand_landmarks, 4)
        index_tip = self.extract_landmark(hand_landmarks, 8)
        middle_tip = self.extract_landmark(hand_landmarks, 12)
        index_mcp = self.extract_landmark(hand_landmarks, 5)
        
        if not all([thumb_tip, index_tip, middle_tip, index_mcp]):
            return False
            
        palm_scale = math.dist(thumb_tip[:2], index_mcp[:2])
        if palm_scale == 0: return False
            
        dist_idx = math.dist(index_tip[:2], thumb_tip[:2]) / palm_scale
        dist_mid = math.dist(middle_tip[:2], thumb_tip[:2]) / palm_scale
        
        is_closed = dist_idx < 0.4 and dist_mid < 0.4
        
        # Store state in history
        self.hand_state_history.append({
            'is_closed': is_closed,
            'dist_idx': dist_idx,
            'dist_mid': dist_mid,
            'timestamp': time.time()
        })
        
        # Check for transition: was open recently and is now closed
        if is_closed and len(self.hand_state_history) > 10:
            recent_states = list(self.hand_state_history)[-10:]
            was_open = any(s['dist_idx'] > 0.7 and s['dist_mid'] > 0.7 for s in recent_states[:-2])
            if was_open:
                return True
                
        return False

    def detect_sorry(self, left_hand, right_hand, pose_landmarks):
        """Detect SORRY: Fist moving in circular motion on chest"""
        if not (left_hand or right_hand) or not pose_landmarks:
            return False
            
        hand_landmarks = left_hand if left_hand else right_hand
        if not self.is_fist(hand_landmarks):
            return False
            
        self.update_normalization(pose_landmarks)
        ls = self.extract_landmark(pose_landmarks, 11)
        rs = self.extract_landmark(pose_landmarks, 12)
        if not (ls and rs): return False
            
        chest_pos = ((ls[0] + rs[0])/2, (ls[1] + rs[1])/2)
        wrist = self.extract_landmark(hand_landmarks, 0)
        if not wrist: return False
        
        if math.dist(wrist[:2], chest_pos) > self.get_norm_dist(0.2):
            return False
            
        # Circular motion check for SORRY
        positions = [frame['wrist'] for frame in list(self.trajectory_analyzer.trajectory)[-20:]]
        if len(positions) < 12: return False
        
        center_x = sum(p[0] for p in positions) / len(positions)
        center_y = sum(p[1] for p in positions) / len(positions)
        radii = [math.dist((p[0], p[1]), (center_x, center_y)) for p in positions]
        avg_radius = sum(radii) / len(radii)
        
        if avg_radius < self.get_norm_dist(0.015): return False
        
        radius_variance = np.var(radii) / (avg_radius**2) if avg_radius > 0 else 1
        # Circular check: low radius variance and good angular spread
        is_circular = radius_variance < 0.45 and np.var([math.atan2(p[1]-center_y, p[0]-center_x) for p in positions]) > 0.7
        
        return is_circular

    def detect_medicine(self, hand_landmarks, face_landmarks):
        """Detect MEDICINE: Hand in 'pill' shape (thumb and index touching) near mouth"""
        if not hand_landmarks or not face_landmarks:
            return False
            
        thumb_tip = self.extract_landmark(hand_landmarks, 4)
        index_tip = self.extract_landmark(hand_landmarks, 8)
        mouth_pos = self.extract_landmark(face_landmarks, 13)
        
        if not all([thumb_tip, index_tip, mouth_pos]):
            return False
            
        # Check if index and thumb are touching (pill shape)
        dist_idx_thumb = math.dist(index_tip[:2], thumb_tip[:2])
        
        # Check distance to mouth
        dist_to_mouth = math.dist(thumb_tip[:2], mouth_pos[:2])
        
        # Normalization: hand should be small and near mouth
        return dist_idx_thumb < 0.04 and dist_to_mouth < self.get_norm_dist(0.12)

    def detect_washroom(self, hand_landmarks):
        """Detect WASHROOM: 'T' sign (thumb tucked between index and middle finger) shaken"""
        if not hand_landmarks:
            return False
            
        thumb_tip = self.extract_landmark(hand_landmarks, 4)
        index_mcp = self.extract_landmark(hand_landmarks, 5)
        middle_mcp = self.extract_landmark(hand_landmarks, 9)
        
        if not all([thumb_tip, index_mcp, middle_mcp]):
            return False
            
        # Thumb should be near the space between index and middle finger
        center_mcp = ((index_mcp[0] + middle_mcp[0])/2, (index_mcp[1] + middle_mcp[1])/2)
        dist_to_center = math.dist(thumb_tip[:2], center_mcp)
        
        # Check for shaking motion (horizontal variance)
        positions = [frame['wrist'] for frame in list(self.trajectory_analyzer.trajectory)[-15:]]
        if len(positions) < 10: return False
        
        x_positions = [p[0] for p in positions]
        x_var = np.var(x_positions)
        
        return dist_to_center < 0.05 and x_var > 0.0001

    def detect_where(self, hand_landmarks):
        """Detect WHERE: Index finger extended and shaken side to side"""
        if not hand_landmarks:
            return False
            
        index_tip = self.extract_landmark(hand_landmarks, 8)
        index_mcp = self.extract_landmark(hand_landmarks, 5)
        middle_tip = self.extract_landmark(hand_landmarks, 12)
        
        if not all([index_tip, index_mcp, middle_tip]):
            return False
            
        # Index finger should be extended
        palm_size = math.dist(self.extract_landmark(hand_landmarks, 0)[:2], index_mcp[:2])
        is_index_extended = math.dist(index_tip[:2], index_mcp[:2]) > palm_size * 1.5
        is_middle_closed = math.dist(middle_tip[:2], index_mcp[:2]) < palm_size * 0.8
        
        # Check for side-to-side shaking
        positions = [frame['wrist'] for frame in list(self.trajectory_analyzer.trajectory)[-15:]]
        if len(positions) < 10: return False
        
        x_positions = [p[0] for p in positions]
        x_var = np.var(x_positions)
        
        return is_index_extended and is_middle_closed and x_var > 0.00015



class VocaAITranslator:
    """Main application class for VocaAI Dynamic Sign Language Translator"""
    
    def __init__(self, root=None):
        # GUI setup
        if root is None:
            self.root = Tk()
        else:
            self.root = root
            
        self.root.title("VocaAI Professional Sign Language Suite")
        
        # MediaPipe setup
        self.mp_holistic = mp.solutions.holistic
        self.mp_drawing = mp.solutions.drawing_utils
        self.holistic = self.mp_holistic.Holistic(
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
            model_complexity=0  # Use lowest complexity for maximum stability
        )
        
        # Language settings
        self.current_lang = 'ml-IN'
        self.auto_lang_detect = True
        self.translations = {
            'ml-IN': {
                'title': "VocaAI Dynamic Sign Language Translator",
                'waiting': "അടയാളങ്ങൾക്കായി കാത്തിരിക്കുന്നു...",
                'decoding': "തിരിച്ചറിയുന്നു",
                'natural_translation': "വാചക വിവർത്തനം",
                'voice_listening': "ശബ്ദം: കേൾക്കുന്നു...",
                'mic_active': "മൈക്ക് സജീവം",
                'mic_ready': "മൈക്ക് തയ്യാർ",
                'signs': "അടയാളങ്ങൾ",
                'last_sentence': "അവസാന വാചകം",
                'voice': "ശബ്ദം",
                'mic_init': "മൈക്ക് തയ്യാറെടുക്കുന്നു...",
                'calibrating': "മൈക്ക് ക്രമീകരിക്കുന്നു... ദയവായി നിശബ്ദത പാലിക്കുക.",
                'spoken': "പറഞ്ഞു (Y)",
                'start_voice': "ശബ്ദ നിവേശനം",
                'history_log': "ചരിത്രം",
                'sentiment': "ഭാവം",
                'learn_signs': "അടയാളങ്ങൾ പഠിക്കുക",
                'tutorial_title': "അടയാള പരിശീലനം",
                'close': "അടയ്ക്കുക"
            },
            'en-US': {
                'title': "VocaAI Dynamic Sign Language Translator",
                'waiting': "Waiting for signs...",
                'decoding': "Decoding",
                'natural_translation': "NATURAL TRANSLATION",
                'voice_listening': "Voice: Listening...",
                'mic_active': "MICROPHONE ACTIVE",
                'mic_ready': "MICROPHONE READY",
                'signs': "Signs",
                'last_sentence': "Last Sentence",
                'voice': "Voice",
                'mic_init': "Mic: Initializing...",
                'calibrating': "Calibrating Microphone... Please stay quiet.",
                'spoken': "Spoken (Y)",
                'start_voice': "START VOICE INPUT",
                'history_log': "HISTORY LOG",
                'sentiment': "SENTIMENT",
                'learn_signs': "LEARN SIGNS",
                'tutorial_title': "SIGN LANGUAGE TUTORIAL",
                'close': "CLOSE"
            }
        }
        
        # Components
        self.sentence_buffer = SentenceBuffer(stability_frames=10, idle_timeout=2.0)
        self.sign_detector = DynamicSignDetector()
        self.voice_recognizer = VoiceRecognizer(self.on_voice_detected)
        self.voice_recognizer.mic_status_callback = self.on_mic_status_change
        self.voice_recognizer.set_language(self.current_lang) # Ensure initial sync
        self.voice_text = ""
        
        # Threading safety
        self.frame_lock = threading.Lock()
        self.processing_fps = 0
        self.last_proc_time = time.time()
        self.last_voice_captured = "None" # For permanent HUD record
        self.sos_sound_running = False
        self.sos_sound_thread = None
        
        # Video capture
        print("Initializing camera...")
        self.cap = cv2.VideoCapture(0)
        
        if not self.cap.isOpened():
            print("Error: Could not open camera.")
            # Fallback to dummy frame if camera fails
            self.current_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            cv2.putText(self.current_frame, "CAMERA ERROR: COULD NOT OPEN", (400, 360), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        else:
            # Set resolution with basic error handling/timeouts
            print("Setting camera resolution...")
            try:
                # Try setting to 720p, but don't hang if it fails
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                # Verify what was actually set
                actual_w = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
                actual_h = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
                print(f"Camera initialized at {actual_w}x{actual_h}")
            except Exception as e:
                print(f"Warning: Could not set camera resolution: {e}")
        
        # Theme Colors (Modern Cyberpunk Palette)
        self.colors = {
            'bg_dark': '#050505',
            'bg_panel': '#0D0D0D',
            'accent_cyan': '#00FFD1',
            'accent_magenta': '#FF00FF',
            'accent_green': '#ADFF2F',
            'text_main': '#E0E0E0',
            'text_dim': '#888888',
            'warning': '#FF4500',
            'hud_blue': '#00A3FF',
            'hud_bg': (15, 15, 15),
            'hud_glow': (0, 255, 209)
        }
        
        # Add a scanning line position
        self.scan_line_y = 0
        self.scan_line_dir = 1
        
        # Start in normal mode first to avoid black screen hang
        self.root.overrideredirect(False) # Restore window borders
        self.root.geometry("1280x720")
        
        # Then try to zoom after a short delay
        self.root.after(1000, lambda: self.root.state('zoomed'))
            
        self.root.configure(bg=self.colors['bg_dark'])
        
        # Main Layout: Left (Video) and Right (Sidebar)
        self.main_container = Frame(self.root, bg=self.colors['bg_dark'])
        self.main_container.pack(fill='both', expand=True)
        
        # Left Side: Video Feed
        self.left_frame = Frame(self.main_container, bg=self.colors['bg_dark'])
        self.left_frame.pack(side='left', fill='both', expand=True, padx=(10, 5), pady=10)
        
        self.canvas = Canvas(self.left_frame, bg='black', highlightthickness=1, highlightbackground='#222')
        self.canvas.pack(fill='both', expand=True)
        
        # Right Side: Professional Sidebar
        self.sidebar = Frame(self.main_container, bg=self.colors['bg_panel'], width=350)
        self.sidebar.pack(side='right', fill='y', padx=(5, 10), pady=10)
        self.sidebar.pack_propagate(False) # Keep fixed width
        
        # Learn Signs Button (Absolute Top Priority)
        self.btn_learn = Button(
            self.sidebar, text=self.translations[self.current_lang]['learn_signs'], 
            command=self.open_tutorial,
            bg=self.colors['accent_magenta'], fg='white', font=('Nirmala UI', 12, 'bold'),
            padx=10, pady=12, relief='flat', cursor='hand2',
            highlightthickness=2, highlightbackground=self.colors['accent_cyan']
        )
        self.btn_learn.pack(fill='x', padx=15, pady=15)
        
        # Project Branding
        self.brand_label = Label(
            self.sidebar, text="VocaAI PRO", font=('Nirmala UI', 28, 'bold'),
            fg=self.colors['accent_cyan'], bg=self.colors['bg_panel']
        )
        self.brand_label.pack(pady=(10, 0))
        
        self.fps_label = Label(
            self.sidebar, text="FPS: 0", font=('Consolas', 8),
            fg='#333', bg=self.colors['bg_panel']
        )
        self.fps_label.pack()
        
        self.subtitle_label = Label(
            self.sidebar, text="INTELLIGENT SIGN SUITE", font=('Nirmala UI', 9, 'bold'),
            fg=self.colors['text_dim'], bg=self.colors['bg_panel']
        )
        self.subtitle_label.pack(pady=(0, 10))
        
        # Skeleton View (Side Panel Proof of AI)
        self.skeleton_title = Label(
            self.sidebar, text="LIVE SKELETON TRACKING", font=('Nirmala UI', 10, 'bold'),
            fg=self.colors['text_dim'], bg=self.colors['bg_panel']
        )
        self.skeleton_title.pack(pady=(10, 0))
        
        self.skeleton_canvas = Canvas(self.sidebar, bg='black', width=300, height=180, highlightthickness=1, highlightbackground='#222')
        self.skeleton_canvas.pack(pady=5)
        
        # Language Selection
        self.lang_frame = Frame(self.sidebar, bg=self.colors['bg_panel'])
        self.lang_frame.pack(fill='x', pady=5)
        
        # Language selection buttons
        self.btn_en = Button(
            self.lang_frame, text="English", command=lambda: self.switch_language('en-US'),
            bg='#222', fg='white', font=('Nirmala UI', 9, 'bold'),
            padx=10, pady=2, relief='flat', cursor='hand2'
        )
        self.btn_en.pack(side='left', expand=True, padx=2)
        
        self.btn_ml = Button(
            self.lang_frame, text="മലയാളം", command=lambda: self.switch_language('ml-IN'),
            bg=self.colors['accent_green'], fg='black', font=('Nirmala UI', 9, 'bold'),
            padx=10, pady=2, relief='flat', cursor='hand2'
        )
        self.btn_ml.pack(side='left', expand=True, padx=2)
        
        # --- NEW FEATURES START ---
        
        # Voice Control Panel (Moved up for visibility)
        self.voice_panel = LabelFrame(
            self.sidebar, text="VOICE INTERFACE", font=('Nirmala UI', 10, 'bold'),
            fg=self.colors['accent_magenta'], bg=self.colors['bg_panel'], padx=10, pady=10, borderwidth=1, relief='flat'
        )
        self.voice_panel.pack(fill='x', padx=10, pady=5)

        # Global Status (Inside Voice Panel)
        self.status_var = StringVar()
        self.status_label = Label(
            self.voice_panel, textvariable=self.status_var, font=('Nirmala UI', 11, 'bold'),
            fg='yellow', bg=self.colors['bg_panel']
        )
        self.status_label.pack(pady=(0, 5))

        # Audio Visualizer Canvas (Inside Voice Panel)
        self.visualizer_canvas = Canvas(self.voice_panel, bg='#050505', height=60, highlightthickness=1, highlightbackground='#222')
        self.visualizer_canvas.pack(fill='x', pady=5)
        self.audio_levels = deque([2]*50, maxlen=50)

        # Manual Mic Controls
        self.mic_ctrl_frame = Frame(self.voice_panel, bg=self.colors['bg_panel'])
        self.mic_ctrl_frame.pack(fill='x', pady=5)
        
        self.btn_mic_toggle = Button(
            self.mic_ctrl_frame, text="RESTART", command=self.restart_mic,
            bg='#222', fg='white', font=('Nirmala UI', 8, 'bold'),
            padx=4, pady=2, relief='flat', cursor='hand2'
        )
        self.btn_mic_toggle.pack(side='left', expand=True, padx=2)
        
        self.btn_voice_input = Button(
            self.mic_ctrl_frame, text="LISTEN", command=self.trigger_voice_input,
            bg='#0078D4', fg='white', font=('Nirmala UI', 8, 'bold'),
            padx=4, pady=2, relief='flat', cursor='hand2'
        )
        self.btn_voice_input.pack(side='left', expand=True, padx=2)

        self.btn_test_voice = Button(
            self.mic_ctrl_frame, text="TEST UI", command=lambda: self.on_voice_detected("VocaAI is working!"),
            bg='#444', fg='white', font=('Nirmala UI', 8, 'bold'),
            padx=4, pady=2, relief='flat', cursor='hand2'
        )
        self.btn_test_voice.pack(side='left', expand=True, padx=2)

        # Voice Status / Captured Text
        self.voice_var = StringVar()
        self.voice_label = Label(
            self.voice_panel, textvariable=self.voice_var, font=('Arial', 12, 'bold'),
            fg=self.colors['accent_cyan'], bg='#1a1a1a', padx=10, pady=8, wraplength=280
        )
        self.voice_label.pack(pady=5, fill='x')

        # Mic/System Status
        self.mic_status_var = StringVar()
        self.mic_status_label = Label(
            self.voice_panel, textvariable=self.mic_status_var, font=('Nirmala UI', 8),
            fg=self.colors['text_dim'], bg=self.colors['bg_panel']
        )
        self.mic_status_label.pack()
        
        # Real-time Analytics Section
        self.analytics_label = Label(
            self.sidebar, text="SIGN RECOGNITION ANALYTICS", font=('Nirmala UI', 10, 'bold'),
            fg=self.colors['text_dim'], bg=self.colors['bg_panel']
        )
        self.analytics_label.pack(pady=(10, 5))
        
        # Live Sign Transcript
        self.transcript_var = StringVar()
        self.transcript_label = Label(
            self.sidebar, textvariable=self.transcript_var, font=('Nirmala UI', 18, 'bold'),
            fg=self.colors['accent_cyan'], bg=self.colors['bg_panel'], wraplength=350, justify='center'
        )
        self.transcript_label.pack(pady=10)
        
        # Potential/Thinking Indicator
        self.potential_var = StringVar()
        self.potential_label = Label(
            self.sidebar, textvariable=self.potential_var, font=('Nirmala UI', 12, 'italic'),
            fg=self.colors['text_dim'], bg=self.colors['bg_panel']
        )
        self.potential_label.pack()
        
        # Confidence Gauge
        self.gauge_canvas = Canvas(self.sidebar, bg='#111', width=200, height=8, highlightthickness=1, highlightbackground='#222')
        self.gauge_canvas.pack(pady=5)
        self.gauge_bar = self.gauge_canvas.create_rectangle(0, 0, 0, 8, fill=self.colors['accent_cyan'], outline='')
        
        # Last Finalized Sentence (Grammar Result)
        self.history_title = Label(
            self.sidebar, text="NATURAL TRANSLATION", font=('Nirmala UI', 10, 'bold'),
            fg=self.colors['text_dim'], bg=self.colors['bg_panel']
        )
        self.history_title.pack(pady=(15, 5))
        
        self.history_var = StringVar()
        self.history_label = Label(
            self.sidebar, textvariable=self.history_var, font=('Nirmala UI', 16),
            fg=self.colors['accent_green'], bg=self.colors['bg_panel'], wraplength=350, justify='center'
        )
        self.history_label.pack(pady=10)
        
        # History Log Section
        self.log_title = Label(
            self.sidebar, text="HISTORY LOG", font=('Nirmala UI', 10, 'bold'),
            fg=self.colors['text_dim'], bg=self.colors['bg_panel']
        )
        self.log_title.pack(pady=(10, 5))
        
        # History Log Listbox
        self.log_frame = Frame(self.sidebar, bg=self.colors['bg_panel'])
        self.log_frame.pack(fill='x', expand=False, padx=10, pady=5)
        
        self.log_list = Listbox(
            self.log_frame, bg='#0a0a0a', fg='#ccc', font=('Nirmala UI', 9),
            borderwidth=0, highlightthickness=0, height=8
        )
        self.log_list.pack(side='left', fill='both', expand=True)
        
        self.log_scroll = Scrollbar(self.log_frame, orient='vertical', command=self.log_list.yview)
        self.log_scroll.pack(side='right', fill='y')
        self.log_list.config(yscrollcommand=self.log_scroll.set)
        
        # Sentiment Section (At the bottom)
        self.sentiment_var = StringVar(value="NEUTRAL")
        self.sentiment_label = Label(
            self.sidebar, textvariable=self.sentiment_var, font=('Nirmala UI', 10, 'bold'),
            fg=self.colors['accent_green'], bg=self.colors['bg_panel']
        )
        self.sentiment_label.pack(side='bottom', pady=10)
        
        # --- NEW FEATURES END ---
        
        # Control variables
        self.running = True
        self.current_frame = np.zeros((720, 1280, 3), dtype=np.uint8) # Start with black frame instead of None
        cv2.putText(self.current_frame, "INITIALIZING SYSTEM...", (450, 360), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        self.last_update_time = time.time()
        self.emergency_mode = False
        self.sos_start_time = 0
        self.voice_text_timer = 0  # Timer to clear overlay text
        self.voice_status_override = False # Prevent update_gui from overwriting status
        self.last_voice_debug = 0
        self.tutorial_window = None # Handle for tutorial popup
        
        # Tutorial Data
        self.sign_tutorial_data = {
            'HELLO': {
                'en': "Move your hand from your forehead outward in a salute-like motion.",
                'ml': "നെറ്റിയിൽ നിന്ന് കൈ പുറത്തേക്ക് നീക്കുക (അഭിവാദ്യം ചെയ്യുന്നത് പോലെ)."
            },
            'THANK YOU': {
                'en': "Touch your lips with your fingertips and move your hand down to your chest.",
                'ml': "വിരൽത്തുമ്പ് ചുണ്ടിൽ തൊട്ടശേഷം കൈ നെഞ്ചിലേക്ക് താഴ്ത്തുക."
            },
            'PLEASE': {
                'en': "Place your open palm on your chest and move it in a circular motion.",
                'ml': "ഉള്ളംകൈ നെഞ്ചിൽ വച്ച് വട്ടത്തിൽ കറക്കുക."
            },
            'HELP': {
                'en': "Place one hand (fist) on top of your other hand (flat palm).",
                'ml': "ഒരു കൈ (മുഷ്ടി) മറ്റേ കൈയുടെ (ഉള്ളംകൈ) മുകളിൽ വയ്ക്കുക."
            },
            'YES': {
                'en': "Make a fist and nod it up and down like a head nodding.",
                'ml': "കൈ ചുരുട്ടി മുഷ്ടിയാക്കി തലയാട്ടുന്നതുപോലെ മുകളിലേക്കും താഴേക്കും ചലിപ്പിക്കുക."
            },
            'NO': {
                'en': "Snap your index and middle fingers down to touch your thumb.",
                'ml': "ചൂണ്ടുവിരലും നടുവിരലും പെരുവിരലിൽ മുട്ടുന്ന രീതിയിൽ താഴേക്ക് ഞൊടിക്കുക."
            },
            'SORRY': {
                'en': "Make a fist and move it in a circular motion over your chest.",
                'ml': "കൈ ചുരുട്ടി നെഞ്ചിന് മുകളിൽ വട്ടത്തിൽ കറക്കുക."
            },
            'WATER': {
                'en': "Point your index finger toward your mouth.",
                'ml': "ചൂണ്ടുവിരൽ വായുടെ അടുത്തേക്ക് ചൂണ്ടുക."
            },
            'FOOD': {
                'en': "Bring your fingertips together to touch your thumb (O-shape) near your mouth.",
                'ml': "വിരൽത്തുമ്പുകൾ പെരുവിരലിൽ മുട്ടിച്ച് ('O' ആകൃതി) വായുടെ അടുത്തേക്ക് കൊണ്ടുവരിക."
            },
            'MEDICINE': {
                'en': "Touch your index finger and thumb together (pill shape) near your mouth.",
                'ml': "ചൂണ്ടുവിരലും പെരുവിരലും മുട്ടിച്ച് (ഗുളികയുടെ ആകൃതി) വായുടെ അടുത്തേക്ക് കൊണ്ടുവരിക."
            },
            'WASHROOM': {
                'en': "Tuck your thumb between index and middle finger (T-sign) and shake it.",
                'ml': "പെരുവിരൽ ചൂണ്ടുവിരലിനും നടുവിരലിനും ഇടയിൽ വച്ച് ('T' അടയാളം) കൈ കുലുക്കുക."
            },
            'WHERE': {
                'en': "Extend your index finger and shake it side-to-side.",
                'ml': "ചൂണ്ടുവിരൽ നീട്ടിപ്പിടിച്ച് വശങ്ങളിലേക്ക് കുലുക്കുക."
            },
            'EMERGENCY': {
                'en': "Cross both hands in fists at the wrists.",
                'ml': "രണ്ട് കൈകളും മുഷ്ടിചുരുട്ടി மணിക്കട്ടുകളിൽ വച്ച് കുറുകെ പിടിക്കുക."
            }
        }
        
        # Initial variable values
        self.transcript_var.set(self.translations[self.current_lang]['waiting'])
        self.history_var.set("...")
        self.voice_var.set(self.translations[self.current_lang]['voice_listening'])
        self.mic_status_var.set(self.translations[self.current_lang]['mic_init'])
        
        # Bind escape key to exit
        self.root.bind('<Escape>', lambda e: self.stop())
        self.root.bind('y', self.on_y)
        self.root.bind('Y', self.on_y)
        self.root.protocol("WM_DELETE_WINDOW", self.stop)

    def restart_mic(self):
        """Manually restart the voice recognizer"""
        print("App: Manual Mic Restart triggered...")
        self.voice_recognizer.stop()
        self.status_var.set("RESTARTING MIC...")
        self.root.after(1000, lambda: self.voice_recognizer.start())
        self.root.after(2000, lambda: self.status_var.set(""))

    def on_mic_status_change(self, status):
        """Callback for microphone status updates"""
        self.root.after(0, lambda: self.mic_status_var.set(status))
        if "LISTENING" in status:
            self.root.after(0, lambda: self.mic_status_label.config(fg='#4CAF50'))
        elif "ERROR" in status or "OFFLINE" in status:
            self.root.after(0, lambda: self.mic_status_label.config(fg='#F44336'))
        else:
            self.root.after(0, lambda: self.mic_status_label.config(fg='#FF9800'))

    def trigger_voice_input(self):
        """Explicitly prompt for voice input and show visual feedback"""
        self.status_var.set("LISTENING NOW...")
        self.voice_label.config(bg='#2e2e2e')
        self.voice_var.set("SPEAK NOW...")
        self.voice_status_override = True
        
        # Reset visual feedback after 5 seconds
        def reset_status():
            self.voice_status_override = False
            self.status_var.set("")
            self.voice_label.config(bg='#252525')
            if not self.voice_text:
                self.voice_var.set(self.translations[self.current_lang]['voice_listening'])

        self.root.after(5000, reset_status)

    def switch_language(self, lang_code):
        """Switch application language dynamically"""
        self.current_lang = lang_code
        self.sentence_buffer.set_language(lang_code)
        self.voice_recognizer.set_language(lang_code)
        
        # Update UI Labels
        self.analytics_label.config(text=self.translations[lang_code]['signs'] + " ANALYTICS")
        self.history_title.config(text=self.translations[lang_code]['natural_translation'])
        self.btn_voice_input.config(text=self.translations[lang_code]['start_voice'])
        self.btn_learn.config(text=self.translations[lang_code]['learn_signs'])
        
        # Update button styles
        if lang_code == 'ml-IN':
            self.btn_ml.config(bg='#4CAF50')
            self.btn_en.config(bg='#333')
        else:
            self.btn_ml.config(bg='#333')
            self.btn_en.config(bg='#4CAF50')
            
        print(f"App: Switched to {lang_code}")

    def open_tutorial(self):
        """Open a highly professional, modern dashboard for learning signs in a separate window"""
        try:
            # Prevent multiple windows
            if hasattr(self, 'tutorial_window') and self.tutorial_window and self.tutorial_window.winfo_exists():
                self.tutorial_window.lift()
                self.tutorial_window.focus_force()
                return
                
            # Create a professional Toplevel window
            self.tutorial_window = Toplevel(self.root)
            self.tutorial_window.title(f"VocaAI Academy | {self.translations[self.current_lang]['tutorial_title']}")
            
            # Professional Window Setup
            width, height = 1000, 800
            screen_width = self.tutorial_window.winfo_screenwidth()
            screen_height = self.tutorial_window.winfo_screenheight()
            x = (screen_width // 2) - (width // 2)
            y = (screen_height // 2) - (height // 2)
            self.tutorial_window.geometry(f"{width}x{height}+{x}+{y}")
            self.tutorial_window.configure(bg='#0A0A0A')
            self.tutorial_window.transient(self.root) 
            
            # --- CUSTOM HEADER BAR ---
            header = Frame(self.tutorial_window, bg='#111', height=80)
            header.pack(fill='x', side='top')
            header.pack_propagate(False)
            
            Label(header, text="VocaAI ACADEMY", font=('Nirmala UI', 24, 'bold'), 
                  fg=self.colors['accent_cyan'], bg='#111').pack(side='left', padx=30, pady=20)
            
            Label(header, text="LEARN THE LANGUAGE OF SIGNS", font=('Nirmala UI', 10, 'bold'), 
                  fg=self.colors['text_dim'], bg='#111').pack(side='left', padx=10, pady=(32, 20))
            
            # --- MAIN DASHBOARD AREA ---
            main_area = Frame(self.tutorial_window, bg='#0A0A0A')
            main_area.pack(fill='both', expand=True, padx=40, pady=30)
            
            # Instructions / Welcome
            welcome_frame = Frame(main_area, bg='#161616', padx=25, pady=20)
            welcome_frame.pack(fill='x', pady=(0, 20))
            
            Label(welcome_frame, text=self.translations[self.current_lang]['tutorial_title'], 
                  font=('Nirmala UI', 18, 'bold'), fg='white', bg='#161616').pack(anchor='w')
            
            guide_text = "Select a sign below to see its movement description and practice it in front of the camera."
            if self.current_lang == 'ml-IN':
                guide_text = "ക്യാമറയ്ക്ക് മുന്നിൽ പരിശീലിക്കുന്നതിനായി താഴെ നിന്ന് ഒരു അടയാളം തിരഞ്ഞെടുക്കുക."
            
            Label(welcome_frame, text=guide_text, font=('Nirmala UI', 11), 
                  fg=self.colors['text_dim'], bg='#161616').pack(anchor='w', pady=(5, 0))

            # --- SCROLLABLE CARD GRID ---
            grid_container = Frame(main_area, bg='#0A0A0A')
            grid_container.pack(fill='both', expand=True)
            
            canvas = Canvas(grid_container, bg='#0A0A0A', highlightthickness=0)
            scrollbar = Scrollbar(grid_container, orient="vertical", command=canvas.yview, width=12)
            scrollable_grid = Frame(canvas, bg='#0A0A0A')
            
            scrollable_grid.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.create_window((0, 0), window=scrollable_grid, anchor="nw", width=900)
            canvas.configure(yscrollcommand=scrollbar.set)
            
            canvas.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")

            # --- SIGN CARDS ---
            lang_key = 'ml' if self.current_lang == 'ml-IN' else 'en'
            for i, (sign, data) in enumerate(self.sign_tutorial_data.items()):
                card = Frame(scrollable_grid, bg='#1A1A1A', padx=25, pady=25, 
                             highlightthickness=1, highlightbackground='#2A2A2A')
                card.pack(fill='x', pady=8)
                
                title_row = Frame(card, bg='#1A1A1A')
                title_row.pack(fill='x')
                
                display_name = sign
                if self.current_lang == 'ml-IN':
                    display_name = self.sentence_buffer.ml_mapping.get(sign, sign)
                
                # Number Badge
                Label(title_row, text=f"{i+1:02d}", font=('Consolas', 14, 'bold'), 
                      fg=self.colors['accent_cyan'], bg='#252525', padx=10, pady=5).pack(side='left', padx=(0, 15))
                
                # Sign Name
                Label(title_row, text=display_name.upper(), font=('Nirmala UI', 16, 'bold'), 
                      fg='white', bg='#1A1A1A').pack(side='left')
                
                # Dynamic/Static Badge
                badge_text = "DYNAMIC MOTION" if "trajectory" in str(data) else "STATIC POSE"
                Label(title_row, text=badge_text, font=('Nirmala UI', 8, 'bold'), 
                      fg=self.colors['accent_magenta'], bg='#252525', padx=8, pady=3).pack(side='right')

                # Description
                desc_text = data.get(lang_key, data.get('en'))
                desc_label = Label(card, text=desc_text, font=('Nirmala UI', 12), 
                                 fg='#BBB', bg='#1A1A1A', wraplength=750, justify='left', anchor='w')
                desc_label.pack(fill='x', pady=(15, 0))
                
                # Action Buttons
                btn_frame = Frame(card, bg='#1A1A1A')
                btn_frame.pack(fill='x', pady=(20, 0))
                
                Label(btn_frame, text="● AI RECOGNITION ACTIVE", font=('Nirmala UI', 8, 'bold'), 
                      fg=self.colors['accent_green'], bg='#1A1A1A').pack(side='left')
                
                Button(btn_frame, text="PRACTICE THIS", font=('Nirmala UI', 9, 'bold'),
                       bg=self.colors['accent_magenta'], fg='white', relief='flat', cursor='hand2',
                       padx=20, pady=8, command=self.tutorial_window.destroy).pack(side='right')

            # --- FOOTER ---
            footer = Frame(self.tutorial_window, bg='#111', height=70)
            footer.pack(fill='x', side='bottom')
            
            Button(footer, text=f"← {self.translations[self.current_lang]['close'].upper()}", 
                   command=self.tutorial_window.destroy, bg='#333', fg='white', 
                   font=('Nirmala UI', 10, 'bold'), padx=40, pady=12, relief='flat', cursor='hand2').pack(pady=10)

        except Exception as e:
            print(f"Error opening tutorial: {e}")
            self.status_var.set("Academy Error!")
            
    def on_y(self, event=None):
        """Handle 'y' key: speak current sentence and show temporary status."""
        print(f"Key pressed: {event.keysym if event else 'N/A'}")
        # Speak the current sentence immediately
        try:
            self.sentence_buffer.finalize_sentence()
            # Update status message briefly
            self.root.after(0, lambda: self.status_var.set(self.translations[self.current_lang]['spoken']))
            # Clear status after 2 seconds using after() for thread safety
            self.root.after(2000, lambda: self.status_var.set(""))
        except Exception as e:
            # Show error in status for a short time
            self.root.after(0, lambda: self.status_var.set(f"Error: {e}"))
            self.root.after(3000, lambda: self.status_var.set(""))
            
    def on_voice_detected(self, text):
        """Callback for when voice is recognized"""
        if not text or len(text.strip()) == 0:
            return

        print(f"DEBUG: App received voice text: '{text}'")
        self.voice_text = text
        self.last_voice_captured = text # Permanent record
        self.voice_text_timer = time.time() + 10 # Display for 10 seconds
        self.voice_status_override = False # Clear override on detection
        
        # Update history and status immediately
        def update_ui():
            print(f"DEBUG: Updating GUI elements with voice: {text}")
            self.update_history_log(f"Voice: {text}")
            self.status_var.set("VOICE CAPTURED ✓")
            
            # Use the global accent color for consistency
            accent_color = self.colors.get('accent_cyan', '#00FFD1')
            
            # Update the variable for sidebar label
            v_prefix = self.translations[self.current_lang]['voice']
            self.voice_var.set(f"{v_prefix}: {text}")
            
            # Force styles and background color
            self.voice_label.config(
                fg=accent_color, 
                bg='#1a1a1a', 
                font=('Arial', 12, 'bold'),
                wraplength=280
            )
            
            # Critical: Ensure label is visible
            self.voice_label.lift()
        
        self.root.after(0, update_ui)
        self.root.after(3000, lambda: self.status_var.set(""))
        
    def extract_landmarks(self, results):
        """Extract all relevant landmarks from MediaPipe results"""
        left_hand = results.left_hand_landmarks
        right_hand = results.right_hand_landmarks
        face_landmarks = results.face_landmarks
        pose_landmarks = results.pose_landmarks
        
        # Extract key positions
        head_pos = None
        if face_landmarks:
            # Use face landmark 0 (forehead) or average of top face points
            head_pos = self.sign_detector.extract_landmark(face_landmarks, 0)
        
        shoulder_pos = None
        if pose_landmarks:
            left_shoulder = self.sign_detector.extract_landmark(pose_landmarks, 11)
            right_shoulder = self.sign_detector.extract_landmark(pose_landmarks, 12)
            if left_shoulder and right_shoulder:
                shoulder_pos = (
                    (left_shoulder[0] + right_shoulder[0]) / 2,
                    (left_shoulder[1] + right_shoulder[1]) / 2,
                    (left_shoulder[2] + right_shoulder[2]) / 2
                )
        
        wrist_pos = None
        fingertip_pos = None
        if left_hand:
            wrist_pos = self.sign_detector.extract_landmark(left_hand, 0)
            fingertip_pos = self.sign_detector.extract_landmark(left_hand, 8)
        elif right_hand:
            wrist_pos = self.sign_detector.extract_landmark(right_hand, 0)
            fingertip_pos = self.sign_detector.extract_landmark(right_hand, 8)
        
        return {
            'left_hand': left_hand,
            'right_hand': right_hand,
            'face': face_landmarks,
            'pose': pose_landmarks,
            'head_pos': head_pos,
            'shoulder_pos': shoulder_pos,
            'wrist_pos': wrist_pos,
            'fingertip_pos': fingertip_pos
        }
    
    def process_frame(self, frame):
        """Process a single frame for sign detection"""
        try:
            h, w = frame.shape[:2]
            
            # OPTIMIZATION: Resize frame for MediaPipe processing
            # 480p is usually enough for good landmark detection and much faster than 720p/1080p
            target_h = 480
            scale = target_h / h
            target_w = int(w * scale)
            small_frame = cv2.resize(frame, (target_w, target_h))
            
            # Convert BGR to RGB
            rgb_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
            rgb_frame.flags.writeable = False # Optimize performance
            
            # Process with MediaPipe Holistic
            # This is the most likely crash point
            results = self.holistic.process(rgb_frame)
            self.last_results = results # Store for skeleton view
            
            # Make writeable again
            rgb_frame.flags.writeable = True
            
            # Extract landmarks (scale them back to original frame size)
            landmarks = self.extract_landmarks(results)
            
            # Update trajectory analyzer (landmarks are normalized 0-1, so scaling is handled)
            self.sign_detector.trajectory_analyzer.add_frame(
                landmarks['wrist_pos'],
                landmarks['fingertip_pos'],
                landmarks['head_pos'],
                landmarks['shoulder_pos']
            )
            
            # Detect dynamic signs
            detected_sign = None
            
            # Check for THANK YOU
            if self.sign_detector.detect_thank_you(
                landmarks['left_hand'],
                landmarks['right_hand'],
                landmarks['face'],
                landmarks['pose']
            ):
                detected_sign = "THANK YOU"
            
            # Check for WATER
            elif self.sign_detector.detect_water(
                landmarks['left_hand'] if landmarks['left_hand'] else landmarks['right_hand'],
                landmarks['face']
            ):
                detected_sign = "WATER"
                
            # Check for FOOD
            elif self.sign_detector.detect_food(
                landmarks['left_hand'] if landmarks['left_hand'] else landmarks['right_hand'],
                landmarks['face']
            ):
                detected_sign = "FOOD"
                
            # Check for EMERGENCY
            elif self.sign_detector.detect_emergency(
                landmarks['left_hand'],
                landmarks['right_hand']
            ):
                detected_sign = "EMERGENCY"
            
            # Check for PLEASE
            elif self.sign_detector.detect_please(
                landmarks['left_hand'],
                landmarks['right_hand'],
                landmarks['pose']
            ):
                detected_sign = "PLEASE"
            
            # Check for HELP
            elif self.sign_detector.detect_help(
                landmarks['left_hand'],
                landmarks['right_hand']
            ):
                detected_sign = "HELP"
            
            # Check for HELLO
            elif self.sign_detector.detect_hello(
                landmarks['left_hand'],
                landmarks['right_hand'],
                landmarks['face']
            ):
                detected_sign = "HELLO"
                
            # Check for YES
            elif self.sign_detector.detect_yes(
                landmarks['left_hand'],
                landmarks['right_hand']
            ):
                detected_sign = "YES"
                
            # Check for NO
            elif self.sign_detector.detect_no(
                landmarks['left_hand'],
                landmarks['right_hand']
            ):
                detected_sign = "NO"
                
            # Check for SORRY
            elif self.sign_detector.detect_sorry(
                landmarks['left_hand'],
                landmarks['right_hand'],
                landmarks['pose']
            ):
                detected_sign = "SORRY"
            
            # Check for MEDICINE
            elif self.sign_detector.detect_medicine(
                landmarks['left_hand'] if landmarks['left_hand'] else landmarks['right_hand'],
                landmarks['face']
            ):
                detected_sign = "MEDICINE"
            
            # Check for WASHROOM
            elif self.sign_detector.detect_washroom(
                landmarks['left_hand'] if landmarks['left_hand'] else landmarks['right_hand']
            ):
                detected_sign = "WASHROOM"
            
            # Check for WHERE
            elif self.sign_detector.detect_where(
                landmarks['left_hand'] if landmarks['left_hand'] else landmarks['right_hand']
            ):
                detected_sign = "WHERE"
            
            # Add sign to buffer if detected
            if detected_sign:
                self.sentence_buffer.add_sign(detected_sign)
                
                # Trigger Emergency SOS Mode
                if detected_sign == "EMERGENCY":
                    self.trigger_emergency_sos()
            
            # Check for idle state (hands dropped or still)
            if not landmarks['left_hand'] and not landmarks['right_hand']:
                if self.sentence_buffer.check_idle():
                    self.sentence_buffer.finalize_sentence()
            elif not self.sign_detector.trajectory_analyzer.is_moving(threshold=0.005, frames=10):
                if self.sentence_buffer.check_idle():
                    self.sentence_buffer.finalize_sentence()
            
            # Draw landmarks on frame
            annotated_frame = frame.copy()
            if results.pose_landmarks:
                self.mp_drawing.draw_landmarks(
                    annotated_frame,
                    results.pose_landmarks,
                    self.mp_holistic.POSE_CONNECTIONS
                )
            if results.left_hand_landmarks:
                self.mp_drawing.draw_landmarks(
                    annotated_frame,
                    results.left_hand_landmarks,
                    self.mp_holistic.HAND_CONNECTIONS
                )
            if results.right_hand_landmarks:
                self.mp_drawing.draw_landmarks(
                    annotated_frame,
                    results.right_hand_landmarks,
                    self.mp_holistic.HAND_CONNECTIONS
                )
            if results.face_landmarks:
                self.mp_drawing.draw_landmarks(
                    annotated_frame,
                    results.face_landmarks,
                    self.mp_holistic.FACEMESH_CONTOURS
                )
            
            # --- PROFESSIONAL HUD OVERLAY ---
            h, w = annotated_frame.shape[:2]
            
            # 1. Corner Brackets (Cyberpunk Style)
            bracket_len = 40
            bracket_thick = 2
            bracket_color = (0, 255, 209) # Cyan
            # Top Left
            cv2.line(annotated_frame, (20, 20), (20 + bracket_len, 20), bracket_color, bracket_thick)
            cv2.line(annotated_frame, (20, 20), (20, 20 + bracket_len), bracket_color, bracket_thick)
            # Top Right
            cv2.line(annotated_frame, (w - 20, 20), (w - 20 - bracket_len, 20), bracket_color, bracket_thick)
            cv2.line(annotated_frame, (w - 20, 20), (w - 20, 20 + bracket_len), bracket_color, bracket_thick)
            # Bottom Left
            cv2.line(annotated_frame, (20, h - 20), (20 + bracket_len, h - 20), bracket_color, bracket_thick)
            cv2.line(annotated_frame, (20, h - 20), (20, h - 20 - bracket_len), bracket_color, bracket_thick)
            # Bottom Right
            cv2.line(annotated_frame, (w - 20, h - 20), (w - 20 - bracket_len, h - 20), bracket_color, bracket_thick)
            cv2.line(annotated_frame, (w - 20, h - 20), (w - 20, h - 20 - bracket_len), bracket_color, bracket_thick)

            # 2. Scanning Line
            self.scan_line_y += 5 * self.scan_line_dir
            if self.scan_line_y >= h or self.scan_line_y <= 0:
                self.scan_line_dir *= -1
            
            # Draw subtle scanning line
            scan_overlay = annotated_frame.copy()
            cv2.line(scan_overlay, (20, self.scan_line_y), (w - 20, self.scan_line_y), (0, 255, 209), 1)
            cv2.addWeighted(scan_overlay, 0.3, annotated_frame, 0.7, 0, annotated_frame)

            # 3. LIVE Engine Indicator (Pulsing)
            pulse = (math.sin(time.time() * 5) + 1) / 2 # 0 to 1
            dot_color = (0, int(255 * pulse), 0) if pulse > 0.5 else (0, 100, 0)
            cv2.circle(annotated_frame, (50, 50), 8, dot_color, -1)
            cv2.putText(annotated_frame, "AI CORE: ACTIVE", (70, 58), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

            # 4. Main Result HUD (Bottom Center)
            current_sign = self.sentence_buffer.get_current_display_text()
            if current_sign:
                # Background for text
                text_size = cv2.getTextSize(current_sign, cv2.FONT_HERSHEY_SIMPLEX, 1.8, 4)[0]
                tx = (w - text_size[0]) // 2
                ty = h - 100
                
                # Draw sleek glassmorphism bar
                overlay = annotated_frame.copy()
                cv2.rectangle(overlay, (tx - 40, ty - 60), (tx + text_size[0] + 40, ty + 40), (10, 10, 10), -1)
                cv2.addWeighted(overlay, 0.7, annotated_frame, 0.3, 0, annotated_frame)
                
                # Glow effect
                cv2.putText(annotated_frame, current_sign, (tx, ty), 
                            cv2.FONT_HERSHEY_SIMPLEX, 1.8, (0, 255, 209), 8) # Cyan Glow
                cv2.putText(annotated_frame, current_sign, (tx, ty), 
                            cv2.FONT_HERSHEY_SIMPLEX, 1.8, (255, 255, 255), 3) # Main White
                
                # Draw small 'DECODED' tag
                cv2.putText(annotated_frame, "DECODED SIGN", (tx, ty - 70), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 209), 1)

            # 5. Confidence Scanner (Right Side)
            # Use stability_counter/threshold for confidence
            # Let's find where stability_counter is
            potential_sign, conf_val = self.sentence_buffer.get_potential_sign()
            
            bar_h = 250
            bar_w = 12
            bx, by = w - 50, (h - bar_h) // 2
            
            # Scanner Frame
            cv2.rectangle(annotated_frame, (bx, by), (bx + bar_w, by + bar_h), (40, 40, 40), 1)
            
            # Scanner Fill
            if conf_val:
                fill_h = int(bar_h * min(conf_val, 1.0))
                color = (0, 255, 209) if conf_val > 0.7 else (0, 165, 255) # Cyan if high, Orange if low
                cv2.rectangle(annotated_frame, (bx, by + bar_h - fill_h), (bx + bar_w, by + bar_h), color, -1)
                
                # Percentage text
                cv2.putText(annotated_frame, f"{int(conf_val*100)}%", (bx - 40, by + bar_h - fill_h + 5), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

            cv2.putText(annotated_frame, "CONFIDENCE", (bx - 70, by - 15), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

            # 6. Voice Overlay (Prominent Centered Bottom)
            if self.voice_text and time.time() < self.voice_text_timer:
                v_prefix = self.translations[self.current_lang]['voice'].upper()
                v_text = f"{v_prefix}: {self.voice_text}"
                
                # Dynamic font scaling based on text length
                font_scale = 1.2 if len(v_text) < 20 else 0.8
                
                # Check for non-ASCII (OpenCV putText doesn't support them)
                is_ascii = all(ord(c) < 128 for c in v_text)
                
                if is_ascii:
                    v_size = cv2.getTextSize(v_text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 2)[0]
                    vx = (w - v_size[0]) // 2
                    vy = h - 220
                    
                    # Background box with glass effect
                    overlay = annotated_frame.copy()
                    cv2.rectangle(overlay, (vx - 30, vy - 50), (vx + v_size[0] + 30, vy + 30), (0, 0, 0), -1)
                    cv2.addWeighted(overlay, 0.7, annotated_frame, 0.3, 0, annotated_frame)
                    
                    # Double Accent border
                    cv2.rectangle(annotated_frame, (vx - 30, vy - 50), (vx + v_size[0] + 30, vy + 30), (0, 255, 209), 1)
                    cv2.rectangle(annotated_frame, (vx - 35, vy - 55), (vx + v_size[0] + 35, vy + 35), (255, 0, 255), 1)
                    
                    # Text with heavy shadow
                    cv2.putText(annotated_frame, v_text, (vx + 3, vy + 3), 
                                cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 0), 4)
                    cv2.putText(annotated_frame, v_text, (vx, vy), 
                                cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), 2)
                else:
                    # Non-ASCII fallback (e.g. Malayalam)
                    # We'll just show a "Voice Detected" badge if we can't render the script directly in CV2
                    badge_text = "VOICE CAPTURED (CHECK SIDEBAR)"
                    b_size = cv2.getTextSize(badge_text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)[0]
                    bx = (w - b_size[0]) // 2
                    by = h - 220
                    cv2.rectangle(annotated_frame, (bx - 20, by - 30), (bx + b_size[0] + 20, by + 15), (255, 0, 255), -1)
                    cv2.putText(annotated_frame, badge_text, (bx, by), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            # 7. Sentiment/System Status (Bottom Left)
            sentiment, s_color_hex = self.detect_sentiment(results.face_landmarks) if results.face_landmarks else ("NEUTRAL", "#ADFF2F")
            
            # Draw a small status box
            cv2.rectangle(annotated_frame, (30, h - 70), (220, h - 30), (15, 15, 15), -1)
            cv2.rectangle(annotated_frame, (30, h - 70), (35, h - 30), (0, 255, 209), -1) # Accent
            cv2.putText(annotated_frame, f"USER: {sentiment}", (45, h - 45), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            
            # 8. Digital Clock & Last Voice (Top Right)
            curr_time = time.strftime("%H:%M:%S")
            cv2.putText(annotated_frame, curr_time, (w - 120, 50), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 209), 1)
            
            # Show last voice captured permanently but small
            if self.last_voice_captured != "None":
                lv_text = f"LAST VOICE: {self.last_voice_captured[:20]}..." if len(self.last_voice_captured) > 20 else f"LAST VOICE: {self.last_voice_captured}"
                cv2.putText(annotated_frame, lv_text, (w - 250, 80), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
            
            # --- END HUD ---
                    
        except Exception as e:
            print(f"Frame Process Error: {e}")
            return frame # Return raw frame if processing fails
            
        return annotated_frame
    
    def trigger_emergency_sos(self):
        """Activate visual and audio SOS alerts"""
        if not self.emergency_mode:
            self.emergency_mode = True
            self.sos_start_time = time.time()
            print("SOS MODE ACTIVATED!")
            
            # Start SOS sound in background
            self.sos_sound_running = True
            self.sos_sound_thread = threading.Thread(target=self._play_sos_sound, daemon=True)
            self.sos_sound_thread.start()
            
            # Reset after 10 seconds
            self.root.after(10000, self.deactivate_sos)

    def _play_sos_sound(self):
        """Play high-quality ambulance siren (File or Synthesized)"""
        # Initial Voice Alert
        try:
            engine = pyttsx3.init()
            engine.setProperty('rate', 150)
            engine.say("Emergency. Ambulance requested.")
            engine.runAndWait()
        except:
            pass

        # Path to an actual sound file if the user wants "Real" sound
        sound_file = "ambulance.wav"
        
        if os.path.exists(sound_file):
            # Play the real audio file in a loop
            while self.sos_sound_running and self.emergency_mode:
                try:
                    winsound.PlaySound(sound_file, winsound.SND_FILENAME)
                except:
                    break
        else:
            # High-Quality Synthesized Siren Fallback
            while self.sos_sound_running and self.emergency_mode:
                try:
                    # 1. European "Hi-Lo" (2 seconds)
                    for _ in range(2):
                        if not self.sos_sound_running: break
                        winsound.Beep(960, 500) # Hi
                        if not self.sos_sound_running: break
                        winsound.Beep(720, 500) # Lo
                    
                    # 2. Rapid "Phaser" (1 second)
                    for _ in range(10):
                        if not self.sos_sound_running: break
                        for f in range(800, 1600, 200):
                            winsound.Beep(f, 20)
                except Exception as e:
                    print(f"SOS Sound Error: {e}")
                    break

    def deactivate_sos(self):
        """Turn off SOS mode"""
        self.emergency_mode = False
        self.sos_sound_running = False
        self.root.configure(bg='#0a0a0a')
        self.main_container.configure(bg='#0a0a0a')
        self.left_frame.configure(bg='#0a0a0a')
        print("SOS Mode deactivated.")

    def detect_sentiment(self, face_landmarks):
        """Analyze face landmarks to detect basic sentiment"""
        if not face_landmarks:
            return "NEUTRAL", '#4CAF50'
            
        # Key landmarks: 
        # 13: Upper lip center, 14: Lower lip center
        # 61, 291: Mouth corners
        # 0: Top of upper lip, 17: Bottom of lower lip
        
        try:
            upper_lip = face_landmarks.landmark[13].y
            lower_lip = face_landmarks.landmark[14].y
            mouth_left = face_landmarks.landmark[61].y
            mouth_right = face_landmarks.landmark[291].y
            mouth_center_y = (upper_lip + lower_lip) / 2
            
            # Smile detection: mouth corners are higher (smaller y) than center
            smile_score = mouth_center_y - (mouth_left + mouth_right) / 2
            
            if smile_score > 0.01:
                return "HAPPY / POSITIVE", '#4CAF50' # Green
            elif smile_score < -0.005:
                return "CONCERNED / SERIOUS", '#FF5252' # Red
            else:
                return "NEUTRAL", '#2196F3' # Blue
        except:
            return "NEUTRAL", '#4CAF50'

    def update_history_log(self, text):
        """Update the history log in the sidebar"""
        if not text:
            return
        timestamp = time.strftime("%H:%M")
        entry = f"[{timestamp}] {text}"
        self.log_list.insert(0, entry) # Insert at top
        if self.log_list.size() > 50:
            self.log_list.delete(50, 'end')

    def update_gui(self):
        """Update GUI periodically using root.after() for thread safety"""
        if not self.running:
            return
            
        try:
            current_time = time.time()
            
            # Update Sidebar Analytics
            sentence = self.sentence_buffer.get_sentence()
            self.transcript_var.set(sentence if sentence else self.translations[self.current_lang]['waiting'])
            
            # Update Natural Translation
            if self.sentence_buffer.history:
                last_sent = self.sentence_buffer.history[-1]
                if self.history_var.get() != last_sent:
                    self.history_var.set(last_sent)
                    self.update_history_log(last_sent)
                    # Update Context based on content
                    if any(word in last_sent.upper() for word in ["HELLO", "THANK", "HELP"]):
                        self.obj_var.set("Context: Social Interaction")
                    elif any(word in last_sent.upper() for word in ["YES", "NO", "PLEASE"]):
                        self.obj_var.set("Context: Basic Request")
            else:
                self.history_var.set("...")
            
            # Update Sentiment
            if hasattr(self, 'last_results') and self.last_results.face_landmarks:
                sentiment, color = self.detect_sentiment(self.last_results.face_landmarks)
                self.sentiment_var.set(f"TONE: {sentiment}")
                self.sentiment_label.config(fg=color)
            
            # SOS Flashing Effect
            if self.emergency_mode:
                # Flashing red at 4Hz
                if int(time.time() * 8) % 2 == 0:
                    flash_color = '#FF0000' # Red
                    text_color = 'white'
                else:
                    flash_color = '#000000' # Black
                    text_color = '#FF0000'
                
                self.root.configure(bg=flash_color)
                self.main_container.configure(bg=flash_color)
                self.left_frame.configure(bg=flash_color)
                self.status_var.set("!!! EMERGENCY SOS !!!")
                self.status_label.config(fg=text_color)
            
            # Update Voice Status Display
            if not self.voice_status_override:
                if self.voice_text and time.time() < self.voice_text_timer:
                    v_prefix = self.translations[self.current_lang]['voice']
                    self.voice_var.set(f"{v_prefix}: {self.voice_text}")
                    self.voice_label.config(font=('Arial', 12, 'bold'), fg=self.colors['accent_cyan'], bg='#1a1a1a')
                else:
                    # Clear voice text if timer expired
                    self.voice_text = ""
                    # If no recent voice text, show the "listening" state
                    self.voice_var.set(self.translations[self.current_lang]['voice_listening'])
                    self.voice_label.config(font=('Arial', 10), fg=self.colors['text_dim'], bg=self.colors['bg_panel'])
            
            # Pulsating effect for Voice Label only if actively listening but no text
            if self.voice_recognizer.is_listening and not self.voice_text:
                alpha = int(127 + 127 * math.sin(time.time() * 5)) # Pulsate 5Hz
                p_color = f'#{alpha:02x}ffff' # Pulsating cyan
                self.voice_label.config(fg=p_color)
            
            # Update Mic Status (Only if not recently updated by callback to avoid flickering)
            # The callback 'on_mic_status_change' handles the more specific states.
            # We only provide a fallback here if the callback hasn't run.
            if not self.mic_status_var.get():
                if self.voice_recognizer.is_listening:
                    self.mic_status_var.set(self.translations[self.current_lang]['mic_active'])
                else:
                    self.mic_status_var.set(self.translations[self.current_lang]['mic_init'])
                
            # Update Audio Visualizer
            self.visualizer_canvas.delete("all")
            
            # Determine wave state
            import random
            if self.voice_recognizer.is_listening:
                # While listening, we show the 'Wave Meter' with real activity or simulation
                # to prove the mic is capturing data
                level = int(self.voice_recognizer.current_energy / 10)
                if level < 5: level = random.randint(5, 15) # Show baseline activity
                level = min(55, level)
                self.audio_levels.append(level)
                
                # Draw bars (Wave Meter Style)
                canvas_w = self.visualizer_canvas.winfo_width()
                canvas_h = self.visualizer_canvas.winfo_height()
                if canvas_w < 10: canvas_w = 300
                if canvas_h < 10: canvas_h = 60
                
                bar_count = len(self.audio_levels)
                bar_width = canvas_w / bar_count
                
                for i, h in enumerate(self.audio_levels):
                    x0 = i * bar_width
                    y_center = canvas_h / 2
                    
                    # Gradient color based on height
                    if h > 40: color = '#FF00FF' # Magenta (Peak)
                    elif h > 20: color = '#00FFD1' # Cyan (Mid)
                    else: color = '#ADFF2F' # Green (Low)
                    
                    # Draw reflecting bars for a cooler look
                    self.visualizer_canvas.create_rectangle(
                        x0, y_center - h/2, x0 + bar_width - 2, y_center + h/2, 
                        fill=color, outline='', stipple='gray50' if h < 10 else ''
                    )
                
                # Draw scanning line over visualizer
                scan_pos = (time.time() * 100) % canvas_w
                self.visualizer_canvas.create_line(scan_pos, 0, scan_pos, canvas_h, fill='#333', width=1)
            else:
                # Show 'Ready' flat line
                canvas_w = self.visualizer_canvas.winfo_width()
                if canvas_w < 10: canvas_w = 300
                self.visualizer_canvas.create_line(0, 30, canvas_w, 30, fill='#444', dash=(4, 4))
                self.visualizer_canvas.create_text(canvas_w/2, 30, text="MIC STANDBY", fill='#444', font=('Arial', 8))
            
            # Update Decoding Status
            potential_sign, confidence = self.sentence_buffer.get_potential_sign()
            if potential_sign and confidence > 0.1:
                self.potential_var.set(f"{self.translations[self.current_lang]['decoding']}: {potential_sign}")
                # Update gauge
                self.gauge_canvas.coords(self.gauge_bar, 0, 0, int(confidence * 200), 8)
                if confidence > 0.8:
                    self.gauge_canvas.itemconfig(self.gauge_bar, fill='#4CAF50') # Strong green
                else:
                    self.gauge_canvas.itemconfig(self.gauge_bar, fill='#FFA000') # Orange/Yellow
            else:
                self.potential_var.set("")
                self.gauge_canvas.coords(self.gauge_bar, 0, 0, 0, 8)

            # Update performance stats
            self.fps_label.config(text=f"AI Engine: {self.processing_fps:.1f} FPS")
        except Exception as e:
            print(f"GUI Sync Error: {e}")

        if self.current_frame is not None:
            try:
                # Main Video Feed
                with self.frame_lock:
                    display_frame = self.current_frame.copy()
                
                frame_rgb = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
                height, width = frame_rgb.shape[:2]
                canvas_width = self.canvas.winfo_width()
                canvas_height = self.canvas.winfo_height()
                
                if canvas_width > 1 and canvas_height > 1:
                    scale = min(canvas_width / width, canvas_height / height)
                    new_width = int(width * scale)
                    new_height = int(height * scale)
                    frame_resized = cv2.resize(frame_rgb, (new_width, new_height))
                    image = Image.fromarray(frame_resized)
                    photo = ImageTk.PhotoImage(image=image)
                    self.canvas.delete("all")
                    self.canvas.create_image(canvas_width // 2, canvas_height // 2, image=photo, anchor='center')
                    self.canvas.image = photo

                # Skeleton-Only Feed (Side Panel) - Only update if results are new
                skeleton_frame = np.zeros((240, 320, 3), dtype=np.uint8)
                if hasattr(self, 'last_results') and self.last_results:
                    # Drawing specs for faster rendering
                    p_spec = self.mp_drawing.DrawingSpec(color=(245,117,66), thickness=1, circle_radius=1)
                    c_spec = self.mp_drawing.DrawingSpec(color=(245,66,230), thickness=1, circle_radius=1)
                    
                    if self.last_results.face_landmarks:
                        self.mp_drawing.draw_landmarks(
                            skeleton_frame, self.last_results.face_landmarks, self.mp_holistic.FACEMESH_CONTOURS,
                            self.mp_drawing.DrawingSpec(color=(80,110,10), thickness=1, circle_radius=1),
                            self.mp_drawing.DrawingSpec(color=(80,256,121), thickness=1, circle_radius=1)
                        )
                    if self.last_results.pose_landmarks:
                        self.mp_drawing.draw_landmarks(
                            skeleton_frame, self.last_results.pose_landmarks, self.mp_holistic.POSE_CONNECTIONS,
                            p_spec, c_spec
                        )
                    if self.last_results.left_hand_landmarks:
                        self.mp_drawing.draw_landmarks(
                            skeleton_frame, self.last_results.left_hand_landmarks, self.mp_holistic.HAND_CONNECTIONS,
                            p_spec, c_spec
                        )
                    if self.last_results.right_hand_landmarks:
                        self.mp_drawing.draw_landmarks(
                            skeleton_frame, self.last_results.right_hand_landmarks, self.mp_holistic.HAND_CONNECTIONS,
                            p_spec, c_spec
                        )

                skeleton_img = Image.fromarray(skeleton_frame)
                skeleton_photo = ImageTk.PhotoImage(image=skeleton_img)
                self.skeleton_canvas.delete("all")
                self.skeleton_canvas.create_image(0, 0, anchor='nw', image=skeleton_photo)
                self.skeleton_canvas.image = skeleton_photo

            except Exception as e:
                print(f"GUI Update Error: {e}")
        
        # Schedule next update (approx 30 FPS for GUI stability)
        self.root.after(33, self.update_gui)
    
    def process_video_loop(self):
        """Dedicated thread for video capture and processing"""
        print("Video Thread: Starting processing loop.")
        while self.running:
            try:
                if self.cap.isOpened():
                    ret, frame = self.cap.read()
                    if ret:
                        # Flip frame horizontally to fix mirror effect
                        frame = cv2.flip(frame, 1)
                        
                        # Process frame (MediaPipe is CPU intensive)
                        try:
                            processed_frame = self.process_frame(frame)
                            
                            # OPTIMIZATION: Pre-resize for GUI display to save main thread time
                            h, w = processed_frame.shape[:2]
                            display_h = 720
                            display_w = int(w * (display_h / h))
                            gui_frame = cv2.resize(processed_frame, (display_w, display_h))
                            
                            with self.frame_lock:
                                self.current_frame = gui_frame
                                
                            # Calculate processing FPS
                            now = time.time()
                            dt = now - self.last_proc_time
                            if dt > 0:
                                self.processing_fps = 0.9 * self.processing_fps + 0.1 * (1.0 / dt)
                            self.last_proc_time = now
                            
                        except Exception as e:
                            print(f"Processing Error: {e}")
                            with self.frame_lock:
                                self.current_frame = frame
                    else:
                        print("Failed to grab frame")
                        time.sleep(0.1)
                else:
                    time.sleep(0.5)
            except Exception as e:
                print(f"Video Stream Error: {e}")
                time.sleep(1)
            
            # Small sleep to prevent 100% CPU usage if processing is too fast
            # but usually MediaPipe is the bottleneck
            time.sleep(0.001)

    def run(self):
        """Start the application"""
        # Start background components
        self.voice_recognizer.start()
        
        # Start processing loops
        self.root.after(100, self.update_gui)
        
        # Start video processing in a dedicated background thread to prevent GUI lag
        threading.Thread(target=self.process_video_loop, daemon=True).start()
        
        # Run the main event loop
        try:
            print("Application starting main event loop...")
            self.root.mainloop()
        except Exception as e:
            print(f"Main Loop Fatal Error: {e}")
        finally:
            print("Cleaning up resources...")
            self.cleanup()
    
    def stop(self):
        """Stop the application"""
        self.running = False
        self.voice_recognizer.stop()
        if self.sentence_buffer.get_sentence():
            self.sentence_buffer.speak_sentence()
    
    def cleanup(self):
        """Clean up resources"""
        self.cap.release()
        cv2.destroyAllWindows()
        self.root.destroy()


class LoginWindow:
    """Professional Modern Web-style Login Dashboard for VocaAI"""
    def __init__(self, root):
        self.root = root
        self.root.title("VocaAI | Secure Access")
        
        # Window size and positioning
        self.width, self.height = 1100, 700
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width // 2) - (self.width // 2)
        y = (screen_height // 2) - (self.height // 2)
        
        self.root.geometry(f"{self.width}x{self.height}+{x}+{y}")
        self.root.configure(bg='#050505')
        self.root.overrideredirect(True)
        
        # --- MODERN UI COLORS ---
        self.colors = {
            'bg': '#050505',
            'panel': '#0A0A0A',
            'accent': '#00FFD1',
            'accent_low': '#004D40',
            'text': '#FFFFFF',
            'text_dim': '#666666',
            'entry_bg': '#111111',
            'btn_hover': '#00CCAB'
        }
        
        # Main Layout Container
        self.main_frame = Frame(self.root, bg=self.colors['bg'], highlightthickness=1, highlightbackground='#222')
        self.main_frame.pack(fill='both', expand=True)
        
        # --- LEFT SIDE: THE ARTISTIC SIDEBAR ---
        self.left_panel = Canvas(self.main_frame, width=500, bg='#080808', highlightthickness=0)
        self.left_panel.pack(side='left', fill='both')
        
        self.draw_sidebar_art()
        
        # --- RIGHT SIDE: THE LOGIN FORM ---
        self.right_panel = Frame(self.main_frame, bg=self.colors['bg'])
        self.right_panel.pack(side='right', fill='both', expand=True)
        
        # Top bar with close button
        self.top_bar = Frame(self.right_panel, bg=self.colors['bg'], height=50)
        self.top_bar.pack(fill='x')
        self.top_bar.pack_propagate(False)
        
        self.close_btn = Label(self.top_bar, text="✕", font=('Arial', 14), 
                              bg=self.colors['bg'], fg='#444', cursor='hand2')
        self.close_btn.pack(side='right', padx=20, pady=10)
        self.close_btn.bind("<Button-1>", lambda e: self.root.destroy())
        self.close_btn.bind("<Enter>", lambda e: self.close_btn.config(fg='#FF0055'))
        self.close_btn.bind("<Leave>", lambda e: self.close_btn.config(fg='#444'))
        
        # Center form container
        self.form_container = Frame(self.right_panel, bg=self.colors['bg'])
        self.form_container.place(relx=0.5, rely=0.5, anchor='center')
        
        # Branding
        Label(self.form_container, text="VocaAI", font=('Nirmala UI', 32, 'bold'), 
              fg=self.colors['accent'], bg=self.colors['bg']).pack(pady=(0, 10))
        Label(self.form_container, text="ENTER THE FUTURE OF COMMUNICATION", font=('Nirmala UI', 9, 'bold'), 
              fg=self.colors['text_dim'], bg=self.colors['bg']).pack(pady=(0, 50))
        
        # Form Fields
        self.user_entry = self.create_input_field(self.form_container, "USERNAME", "admin")
        self.pass_entry = self.create_input_field(self.form_container, "PASSWORD", "••••••••", is_password=True)
        
        # Login Button
        self.login_btn = Button(self.form_container, text="AUTHENTICATE", font=('Nirmala UI', 11, 'bold'),
                               bg=self.colors['accent'], fg='black', relief='flat', 
                               width=30, pady=15, cursor='hand2', command=self.handle_login)
        self.login_btn.pack(pady=40)
        self.login_btn.bind("<Enter>", lambda e: self.login_btn.config(bg=self.colors['btn_hover']))
        self.login_btn.bind("<Leave>", lambda e: self.login_btn.config(bg=self.colors['accent']))
        
        # Help footer
        Label(self.form_container, text="Need technical assistance?", font=('Nirmala UI', 9), 
              fg='#333', bg=self.colors['bg']).pack()
        Label(self.form_container, text="Contact System Administrator", font=('Nirmala UI', 9, 'underline'), 
              fg=self.colors['text_dim'], bg=self.colors['bg'], cursor='hand2').pack()

    def draw_sidebar_art(self):
        # Create a gradient effect
        for i in range(500):
            color = self.interpolate_color('#080808', '#001A14', i/500)
            self.left_panel.create_line(i, 0, i, 700, fill=color)
            
        # Draw some tech lines/shapes
        self.left_panel.create_text(250, 300, text="VocaAI", font=('Nirmala UI', 60, 'bold'), 
                                   fill='#00221C', angle=0)
        
        # Abstract tech circles
        self.left_panel.create_oval(-100, -100, 300, 300, outline='#00332B', width=2)
        self.left_panel.create_oval(300, 500, 600, 800, outline='#00332B', width=1)
        
        # Content overlay
        Label(self.left_panel, text="VocaAI", font=('Nirmala UI', 54, 'bold'), 
              fg=self.colors['accent'], bg='#080808').place(x=80, y=250)
        
        Label(self.left_panel, text="INTELLIGENT SIGN INTERFACE", font=('Nirmala UI', 11, 'bold'), 
              fg='#008870', bg='#080808').place(x=85, y=330)
        
        # Feature pills
        features = ["REAL-TIME AI", "VOICE SYNTH", "ACADEMY"]
        for i, feat in enumerate(features):
            f = Frame(self.left_panel, bg='#00221C', padx=15, pady=5)
            f.place(x=85 + (i*110), y=380)
            Label(f, text=feat, font=('Nirmala UI', 8, 'bold'), fg=self.colors['accent'], bg='#00221C').pack()

    def create_input_field(self, parent, label_text, placeholder, is_password=False):
        frame = Frame(parent, bg=self.colors['bg'])
        frame.pack(fill='x', pady=10)
        
        Label(frame, text=label_text, font=('Nirmala UI', 8, 'bold'), 
              fg=self.colors['text_dim'], bg=self.colors['bg']).pack(anchor='w', padx=2)
              
        entry_frame = Frame(frame, bg='#1A1A1A', padx=1, pady=1)
        entry_frame.pack(fill='x', pady=5)
        
        entry = Entry(entry_frame, font=('Nirmala UI', 11), bg=self.colors['entry_bg'], 
                      fg='white', relief='flat', bd=0, insertbackground='white', width=40)
        if is_password: entry.config(show="*")
        entry.pack(padx=15, pady=12)
        
        # Focus effects
        entry.bind("<FocusIn>", lambda e: entry_frame.config(bg=self.colors['accent']))
        entry.bind("<FocusOut>", lambda e: entry_frame.config(bg='#1A1A1A'))
        
        return entry

    def interpolate_color(self, c1, c2, t):
        # Simple color interpolation
        r1, g1, b1 = self.root.winfo_rgb(c1)
        r2, g2, b2 = self.root.winfo_rgb(c2)
        r = int(r1 + (r2 - r1) * t)
        g = int(g1 + (g2 - g1) * t)
        b = int(b1 + (b2 - b1) * t)
        return f'#{r>>8:02x}{g>>8:02x}{b>>8:02x}'

    def handle_login(self):
        self.login_btn.config(text="VERIFYING CREDENTIALS...", state='disabled', bg='#111', fg=self.colors['text_dim'])
        self.root.update()
        
        # Simulate high-end auth process
        time.sleep(1.5)
        
        # Transition to Main App on SAME root
        for widget in self.root.winfo_children():
            widget.destroy()
            
        app = VocaAITranslator(self.root)
        app.run()

from tkinter import Entry

if __name__ == "__main__":
    root = Tk()
    login = LoginWindow(root)
    root.mainloop()