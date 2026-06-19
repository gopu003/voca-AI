from collections import deque
import math
import time
import numpy as np
import pyttsx3
import threading

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
            "WHERE": "എവിടെ",
            "PAIN": "വേദന",
            "HUNGRY": "വിശക്കുന്നുണ്ട്"
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

            if "PAIN" in text:
                if "MEDICINE" in text: return "എനിക്ക് വേദനയുണ്ട്, ദയവായി മരുന്ന് തരുമോ?"
                return "എനിക്ക് ഇവിടെ വേദനയുണ്ട്."
            
            if "HUNGRY" in text or ("FOOD" in text and "WATER" not in text):
                if "PLEASE" in text: return "എനിക്ക് വളരെ വിശക്കുന്നു, ദയവായി ഭക്ഷണം തരുമോ?"
                return "എനിക്ക് വിശക്കുന്നു."
            
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

    def finalize_sentence(self, speak=True):
        """Finalize current buffer into history and speak it"""
        if not self.buffer:
            return None
            
        sentence = self.formulate_natural_sentence(self.buffer)
        self.history.append(sentence)
        
        # Speak it
        if speak:
            threading.Thread(target=self._speak, args=(sentence,), daemon=True).start()
        
        # Clear for next sentence
        self.buffer.clear()
        self.current_sign = None
        self.sign_window.clear()
        return sentence

    def speak_last_sentence(self):
        """Speak the last finalized sentence from history"""
        if self.history:
            last_sentence = self.history[-1]
            threading.Thread(target=self._speak, args=(last_sentence,), daemon=True).start()
            return last_sentence
        return None
    
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
    
    def is_thumbs_up(self, hand_landmarks):
        """Check if hand is in Thumbs Up position"""
        if not hand_landmarks:
            return False
            
        wrist = self.extract_landmark(hand_landmarks, 0)
        thumb_tip = self.extract_landmark(hand_landmarks, 4)
        thumb_ip = self.extract_landmark(hand_landmarks, 3)
        index_mcp = self.extract_landmark(hand_landmarks, 5)
        pinky_tip = self.extract_landmark(hand_landmarks, 20)
        
        if not all([wrist, thumb_tip, thumb_ip, index_mcp, pinky_tip]):
            return False
            
        # 1. Check if fingers are curled (like a fist)
        # We can reuse is_fist logic partially, but we need thumb to be OUT
        # Simplified: Check if fingertips 8, 12, 16, 20 are below their MCPs or close to palm
        tips = [self.extract_landmark(hand_landmarks, i) for i in [8, 12, 16, 20]]
        mcps = [self.extract_landmark(hand_landmarks, i) for i in [5, 9, 13, 17]]
        
        fingers_folded = True
        for tip, mcp in zip(tips, mcps):
            # In normalized coords (y increases downwards), tip should be lower (greater y) than MCP if hand is upright
            # But hand orientation varies. Better to check distance to wrist vs mcp to wrist.
            if math.dist(tip[:2], wrist[:2]) > math.dist(mcp[:2], wrist[:2]) * 1.2:
                fingers_folded = False
                break
                
        if not fingers_folded:
            return False
            
        # 2. Check if Thumb is extended UPWARD
        # Thumb tip should be significantly higher (lower y) than index MCP
        is_thumb_high = thumb_tip[1] < index_mcp[1]
        
        # Thumb tip should be higher than Thumb IP (pointing up)
        is_thumb_pointing_up = thumb_tip[1] < thumb_ip[1]
        
        return is_thumb_high and is_thumb_pointing_up

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
        wrist = self.extract_landmark(hand_landmarks, 0)
        
        if not all([thumb_tip, index_mcp, middle_mcp, wrist]):
            return False
            
        # Use palm size for normalization so thresholds scale with hand distance
        palm_size = math.dist(wrist[:2], index_mcp[:2])
        if palm_size <= 0:
            return False
        
        # Thumb should be close to the space between index and middle finger (T shape)
        center_mcp = ((index_mcp[0] + middle_mcp[0]) / 2.0, (index_mcp[1] + middle_mcp[1]) / 2.0)
        dist_to_center = math.dist(thumb_tip[:2], center_mcp)
        
        # Require a fairly tight T-shape, relative to palm size
        if dist_to_center > palm_size * 0.35:
            return False
        
        # Check for clear horizontal shaking motion (stronger than tiny jitter)
        traj = list(self.trajectory_analyzer.trajectory)[-20:]
        if len(traj) < 12:
            return False
        
        x_positions = [frame['wrist'][0] for frame in traj if frame.get('wrist') is not None]
        if len(x_positions) < 12:
            return False
        
        x_var = np.var(x_positions)
        x_range = max(x_positions) - min(x_positions)
        
        # Only trigger if there is noticeable side-to-side motion
        return x_var > 0.001 and x_range > palm_size * 0.6

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

    def detect_pain(self, hand_landmarks, pose_landmarks):
        """Detect PAIN: Fist placed on chest with small jitter"""
        if not hand_landmarks or not pose_landmarks:
            return False
        
        if not self.is_fist(hand_landmarks):
            return False
        
        self.update_normalization(pose_landmarks)
        ls = self.extract_landmark(pose_landmarks, 11)
        rs = self.extract_landmark(pose_landmarks, 12)
        if not (ls and rs):
            return False
        
        chest_pos = ((ls[0] + rs[0]) / 2.0, (ls[1] + rs[1]) / 2.0)
        wrist = self.extract_landmark(hand_landmarks, 0)
        if not wrist:
            return False
        
        dist_to_chest = math.dist(wrist[:2], chest_pos[:2])
        if dist_to_chest > self.get_norm_dist(0.15):
            return False
        
        traj = list(self.trajectory_analyzer.trajectory)[-15:]
        if len(traj) < 10:
            return False
        x_positions = [f['wrist'][0] for f in traj]
        y_positions = [f['wrist'][1] for f in traj]
        x_var = np.var(x_positions)
        y_var = np.var(y_positions)
        
        return 0.00002 < (x_var + y_var) < 0.0005

    def detect_hungry(self, hand_landmarks, pose_landmarks):
        """Detect HUNGRY: Open palm moving down from chest toward stomach"""
        if not hand_landmarks or not pose_landmarks:
            return False
        
        if not self.is_open_palm(hand_landmarks):
            return False
        
        self.update_normalization(pose_landmarks)
        ls = self.extract_landmark(pose_landmarks, 11)
        rs = self.extract_landmark(pose_landmarks, 12)
        if not (ls and rs):
            return False
        
        chest_y = (ls[1] + rs[1]) / 2.0
        wrist_start = self.trajectory_analyzer.trajectory[0]['wrist'] if self.trajectory_analyzer.trajectory else None
        wrist_now = self.extract_landmark(hand_landmarks, 0)
        if not (wrist_start and wrist_now):
            return False
        
        vertical_movement = wrist_now[1] - wrist_start[1]
        if vertical_movement < self.get_norm_dist(0.04):
            return False
        
        if not (chest_y < wrist_now[1] < chest_y + self.get_norm_dist(0.25)):
            return False
        
        return True
