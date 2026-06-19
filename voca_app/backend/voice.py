import speech_recognition as sr
import threading
import time
from collections import deque
import numpy as np

class VoiceRecognizer:
    """Handles background speech-to-text recognition"""
    
    def __init__(self, callback, device_index=None):
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
        self.device_index = device_index
        self.device_changed = False
        
        # Use default microphone for better compatibility across systems
        try:
            self._initialize_mic(device_index)
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
        
    def set_device(self, device_index):
        """Set the microphone device index and force re-initialization"""
        self.device_index = device_index
        self.microphone = None
        self.device_changed = True
        print(f"Voice: Device index set to {device_index}. Microphone reset requested.")

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
                    self._initialize_mic(self.device_index)
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
                    
                    loop_count = 0
                    while self.running:
                        if self.device_changed:
                            print("Voice: Device change requested. Restarting listening loop...")
                            self.device_changed = False
                            self.microphone = None
                            break
                        
                        loop_count += 1
                        try:
                            # Heartbeat log every ~10 seconds (assuming 1s timeout)
                            if loop_count % 10 == 0:
                                print(f"DEBUG: Voice loop alive. Energy: {self.current_energy:.2f}")

                            # Listen for a phrase with a shorter timeout for better responsiveness
                            # print("DEBUG: Listening for audio...") 
                            try:
                                audio = self.recognizer.listen(source, timeout=1, phrase_time_limit=10)
                                print("DEBUG: Audio captured, processing...")
                            except sr.WaitTimeoutError:
                                # No speech started
                                raise

                            
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

    def get_available_microphones(self):
        """Returns a list of (index, name) tuples for available microphones"""
        try:
            mics = sr.Microphone.list_microphone_names()
            return [(i, name) for i, name in enumerate(mics)]
        except Exception as e:
            print(f"Error listing microphones: {e}")
            return []

    def _initialize_mic(self, device_index=None):
        """Try to find and initialize a working microphone"""
        try:
            mics = sr.Microphone.list_microphone_names()
            print("\n--- Available Audio Devices ---")
            for i, name in enumerate(mics):
                print(f"Index {i}: {name}")
            
            target_idx = device_index
            
            if target_idx is None:
                # Auto-detect if no specific device requested
                for i, name in enumerate(mics):
                    if any(k in name.lower() for k in ["mic", "audio", "array", "input"]):
                        target_idx = i
                        break
            
            if target_idx is not None and target_idx < len(mics):
                print(f"Voice: Selecting mic index {target_idx}: {mics[target_idx]}")
                self.microphone = sr.Microphone(device_index=target_idx)
                self.device_index = target_idx # Store for future re-inits
            else:
                self.microphone = sr.Microphone()
                print("Voice: Using default system microphone.")
        except Exception as e:
            print(f"Voice: Mic Initialization Failed: {e}")
            self.microphone = None

    def stop(self):
        self.running = False
