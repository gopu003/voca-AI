"""
VocaAI Dynamic Sign Language Translator - Main UI
Frontend entry point for the VocaAI application.
"""

# DO NOT RUN THIS FILE DIRECTLY. Run 'python run.py' in the project root instead.

import os
import sys

# Add project root to sys.path to allow running this file directly for testing
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)

import cv2
import mediapipe as mp
import numpy as np
import math
import threading
import time
import webbrowser
import urllib.parse
from collections import deque
import tkinter as tk
from tkinter import Tk, Canvas, Label, StringVar, Frame, Button, Listbox, Scrollbar, LabelFrame, Toplevel, Checkbutton, BooleanVar, Entry, Radiobutton
from tkinter import ttk
import pyttsx3
from PIL import Image, ImageTk
try:
    import winsound as _winsound
    def _beep(f, d): 
        _winsound.Beep(f, d)
    def _playsnd(p): 
        _winsound.PlaySound(p, _winsound.SND_FILENAME)
except Exception:
    def _beep(f, d): 
        pass
    def _playsnd(p): 
        pass

# Import backend modules
try:
    from voca_app.backend.signs import SentenceBuffer, DynamicSignDetector, TrajectoryAnalyzer
    from voca_app.backend.voice import VoiceRecognizer
    from voca_app.backend.db import DatabaseManager
    from voca_app.backend.network import NetworkClient
    from voca_app.backend.web_server_manager import WebServerManager
    from voca_app.backend.web_server import VocaWebServer
    import queue
except ImportError as e:
    # Fallback for direct execution if sys.path hack fails or structure is different
    print(f"Import Error: {e}")
    print("Ensure you are running from the project root or 'run.py'.")
    # Attempt to add current directory's parent's parent to path if not already
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from voca_app.backend.signs import SentenceBuffer, DynamicSignDetector, TrajectoryAnalyzer
    from voca_app.backend.voice import VoiceRecognizer
    from voca_app.backend.db import DatabaseManager
    from voca_app.backend.network import NetworkClient
    from voca_app.backend.web_server_manager import WebServerManager
    from voca_app.backend.web_server import VocaWebServer
    import queue

class VocaAITranslator:
    """Main application class for VocaAI Dynamic Sign Language Translator"""
    
    def __init__(self, root=None):
        self.running = True
        # Database setup
        self.db = DatabaseManager()
        
        # Network setup
        self.network = NetworkClient()
        self.network.set_callback(self.on_network_message)
        
        # Web Server setup (for Mobile) - queue must exist before manager so callback can put status
        self.web_server_status_queue = queue.Queue()
        self.web_url = None
        # Callback from manager runs in server thread; put status in queue so main thread updates UI (keeps connection reliable)
        def _web_server_status_from_manager(status, data):
            try:
                self.web_server_status_queue.put_nowait((status, data))
            except Exception:
                pass
        self.web_server_manager = WebServerManager(_web_server_status_from_manager)
        self.web_server = VocaWebServer()  # Stub for has_ngrok_auth(); replaced by manager's running server when RUNNING
        self.ngrok_prompt_shown = False
        
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
        
        self.translator = None
        self.teach_mode_active = False
        
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
        
        # Left Side: Video Feed and Data Dashboard
        self.left_frame = Frame(self.main_container, bg=self.colors['bg_dark'])
        self.left_frame.pack(side='left', fill='both', expand=True, padx=(10, 5), pady=10)
        
        # 1. Video Area (Top - Reduced Size)
        self.video_frame = Frame(self.left_frame, bg=self.colors['bg_dark'])
        self.video_frame.pack(side='top', fill='both', expand=True)
        
        self.canvas = Canvas(self.video_frame, bg='black', highlightthickness=1, highlightbackground='#222')
        self.canvas.pack(fill='both', expand=True)

        # 2. Data Dashboard (Bottom - New Feature)
        self.dashboard_height = 220
        self.data_panel = Frame(self.left_frame, bg=self.colors['bg_panel'], height=self.dashboard_height)
        self.data_panel.pack(side='bottom', fill='x', pady=(10, 0))
        self.data_panel.pack_propagate(False)

        # Dashboard Header
        Label(self.data_panel, text="TRANSLATION DASHBOARD", font=('Nirmala UI', 10, 'bold'),
              bg=self.colors['bg_panel'], fg=self.colors['accent_cyan']).pack(anchor='w', padx=10, pady=5)

        # Dashboard Content Grid
        self.dash_content = Frame(self.data_panel, bg=self.colors['bg_panel'])
        self.dash_content.pack(fill='both', expand=True, padx=10, pady=5)

        # Col 2: Recent History (Scrollable) - Expanded to take left side
        self.col2 = Frame(self.dash_content, bg='#1a1a1a')
        self.col2.pack(side='left', fill='both', expand=True, padx=5)
        
        Label(self.col2, text="TRANSLATION HISTORY", font=('Consolas', 9), bg='#1a1a1a', fg='#888').pack(anchor='w', padx=5, pady=5)
        
        self.log_list = Listbox(self.col2, bg='#111', fg='#ddd', font=('Consolas', 9), borderwidth=0, highlightthickness=0)
        self.log_list.pack(side='left', fill='both', expand=True, padx=5, pady=5)
        self.log_scroll = Scrollbar(self.col2, command=self.log_list.yview)
        self.log_scroll.pack(side='right', fill='y')
        self.log_list.config(yscrollcommand=self.log_scroll.set)
        self.log_list.insert(0, "[SYSTEM] VocaAI Engine Started...")
        self.log_list.insert(1, "[SYSTEM] Camera Initialized.")
        self.log_list.insert(2, "[SYSTEM] Voice Module Ready.")

        # Col 3: Confidence/Status Graph (Visual Placeholder)
        self.col3 = Frame(self.dash_content, bg='#1a1a1a', width=350) # Slightly wider
        self.col3.pack(side='right', fill='y', padx=(5, 0))
        self.col3.pack_propagate(False)

        Label(self.col3, text="RECOGNITION METRICS", font=('Consolas', 9), bg='#1a1a1a', fg='#888').pack(anchor='w', padx=5, pady=5)
        
        self.metrics_canvas = Canvas(self.col3, bg='#050505', highlightthickness=0)
        self.metrics_canvas.pack(fill='both', expand=True, padx=5, pady=5)
        # Draw some static grid lines
        for i in range(0, 350, 20):
            self.metrics_canvas.create_line(i, 0, i, 150, fill='#222')
            self.metrics_canvas.create_line(0, i, 350, i, fill='#222')
        
        # Right Side: Professional Sidebar (Scrollable Container)
        self.sidebar_container = Frame(self.main_container, bg=self.colors['bg_panel'], width=350)
        self.sidebar_container.pack(side='right', fill='y', padx=(5, 10), pady=10)
        self.sidebar_container.pack_propagate(False) # Keep fixed width
        
        # Create Canvas for scrolling
        self.sidebar_canvas = Canvas(self.sidebar_container, bg=self.colors['bg_panel'], highlightthickness=0)
        self.sidebar_scroll_y = Scrollbar(self.sidebar_container, orient="vertical", command=self.sidebar_canvas.yview)
        self.sidebar_scroll_x = Scrollbar(self.sidebar_container, orient="horizontal", command=self.sidebar_canvas.xview)
        
        # Create Frame inside Canvas (The actual sidebar content)
        self.sidebar = Frame(self.sidebar_canvas, bg=self.colors['bg_panel']) 
        
        # Link scrollbars
        self.sidebar_window = self.sidebar_canvas.create_window((0, 0), window=self.sidebar, anchor="nw")
        self.sidebar_canvas.configure(yscrollcommand=self.sidebar_scroll_y.set, xscrollcommand=self.sidebar_scroll_x.set)
        
        # Pack scrolling elements
        self.sidebar_scroll_y.pack(side="right", fill="y")
        self.sidebar_scroll_x.pack(side="bottom", fill="x")
        self.sidebar_canvas.pack(side="left", fill="both", expand=True)
        
        # Update scroll region
        def on_frame_configure(event):
            self.sidebar_canvas.configure(scrollregion=self.sidebar_canvas.bbox("all"))
        self.sidebar.bind("<Configure>", on_frame_configure)
        
        # Bind MouseWheel (Windows style)
        def on_mousewheel(event):
            # Check for Shift key (horizontal scrolling)
            if event.state & 0x0001: # Shift key mask
                 self.sidebar_canvas.xview_scroll(int(-1*(event.delta/120)), "units")
            else:
                 self.sidebar_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        # Only bind mousewheel when hovering over sidebar to avoid conflicts
        self.sidebar_container.bind("<Enter>", lambda e: self.sidebar_canvas.bind_all("<MouseWheel>", on_mousewheel))
        self.sidebar_container.bind("<Leave>", lambda e: self.sidebar_canvas.unbind_all("<MouseWheel>"))

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
        
        # NEW: Multi-Language Translation Controls (Top Priority)
        if self.translator:
            self.translation_panel = LabelFrame(
                self.sidebar, text="🌎 TRANSLATION", font=('Nirmala UI', 10, 'bold'),
                fg='#00FFD1', bg=self.colors['bg_panel'], padx=10, pady=10, borderwidth=1, relief='flat'
            )
            self.translation_panel.pack(fill='x', padx=10, pady=5)
            
            # Language Selection
            Label(self.translation_panel, text="Translate To:", font=('Nirmala UI', 9, 'bold'),
                  fg='white', bg=self.colors['bg_panel']).pack(anchor='w', padx=5, pady=(0, 5))
            
            self.translation_var = StringVar()
            self.translation_var.set("English")  # Default
            self.translation_combo = ttk.Combobox(
                self.translation_panel, textvariable=self.translation_var, 
                values=self.translator.get_language_options(), state="readonly",
                font=('Nirmala UI', 9), width=18, height=8
            )
            self.translation_combo.pack(fill='x', padx=5, pady=(0, 10))
            self.translation_combo.bind("<ComboboxSelected>", self.on_translation_language_change)
            
            # Teach Me Mode Toggle
            self.teach_mode_var = BooleanVar(value=False)
            self.teach_mode_btn = Checkbutton(
                self.translation_panel, text="🧠 TEACH ME MODE", variable=self.teach_mode_var,
                command=self.toggle_teach_mode, font=('Nirmala UI', 9, 'bold'),
                bg=self.colors['bg_panel'], fg='#FFD700', selectcolor='#222',
                activebackground=self.colors['bg_panel'], activeforeground='#FFD700'
            )
            self.teach_mode_btn.pack(anchor='w', padx=5)
        
        # Voice Control Panel (Moved down for visibility)
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
        self.visualizer_canvas = Canvas(self.voice_panel, bg='#050505', height=40, highlightthickness=1, highlightbackground='#222')
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

        self.btn_select_mic = Button(
            self.mic_ctrl_frame, text="MIC SELECT", command=self.show_mic_selector,
            bg='#666', fg='white', font=('Nirmala UI', 8, 'bold'),
            padx=4, pady=2, relief='flat', cursor='hand2'
        )
        self.btn_select_mic.pack(side='left', expand=True, padx=2)

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
        
        
        # --- NEW FEATURES START ---
        
        # Network Panel
        self.network_panel = LabelFrame(
            self.sidebar, text="REMOTE CONNECTION", font=('Nirmala UI', 10, 'bold'),
            fg=self.colors['accent_cyan'], bg=self.colors['bg_panel'], padx=10, pady=10, borderwidth=1, relief='flat'
        )
        self.network_panel.pack(fill='x', padx=10, pady=5)
        self.network_frame = self.network_panel # Alias for compatibility
        
        # Old controls removed

        
        # Connection Status (Legacy)
        self.net_status_var = StringVar(value="OFFLINE")
        self.net_status_label = Label(
            self.network_panel, textvariable=self.net_status_var, font=('Nirmala UI', 9),
            fg='#888', bg=self.colors['bg_panel']
        )
        # self.net_status_label.pack(pady=(0, 5)) 
        
        # Connect to Host UI (Legacy but keeping for now)
        self.btn_connect = Button(self.network_panel, text="Connect (Client)", state='disabled') 
        self.ip_entry = Entry(self.network_panel)
        
        # New Cleaner UI Structure
        self.net_ctrl_frame = Frame(self.network_panel, bg=self.colors['bg_panel'])
        self.net_ctrl_frame.pack(fill='x', pady=5)
        
        # IP Input for connecting to others
        Label(self.net_ctrl_frame, text="Partner IP:", fg='#888', bg=self.colors['bg_panel'], font=('Nirmala UI', 8)).pack(side='left', padx=(5, 2))
        
        self.ip_entry = Entry(self.net_ctrl_frame, bg='#222', fg='white', width=15, relief='flat', font=('Consolas', 10))
        self.ip_entry.insert(0, "") # Empty by default to force user input
        self.ip_entry.pack(side='left', padx=2, fill='y')
        
        self.btn_connect = Button(
            self.net_ctrl_frame, text="JOIN (Enter IP)", command=self.connect_network,
            bg='#0078D4', fg='white', font=('Nirmala UI', 8, 'bold'),
            padx=5, pady=2, relief='flat', cursor='hand2'
        )
        self.btn_connect.pack(side='left', padx=2)
        
        self.btn_remote_join = Button(
            self.net_ctrl_frame, text="JOIN (WEB)", command=self.join_remote_session,
            bg='#00BCD4', fg='white', font=('Nirmala UI', 8, 'bold'),
            padx=5, pady=2, relief='flat', cursor='hand2'
        )
        self.btn_remote_join.pack(side='left', padx=2)
        
        self.btn_host = Button(
            self.net_ctrl_frame, text="HOST", command=self.host_network,
            bg='#4CAF50', fg='white', font=('Nirmala UI', 8, 'bold'),
            padx=5, pady=2, relief='flat', cursor='hand2'
        )
        self.btn_host.pack(side='left', padx=2)
        
        self.btn_reset = Button(
            self.net_ctrl_frame, text="RESET", command=self.reset_network,
            bg='#D32F2F', fg='white', font=('Nirmala UI', 8, 'bold'),
            padx=5, pady=2, relief='flat', cursor='hand2'
        )
        self.btn_reset.pack(side='left', padx=2)
        
        def _open_share_dialog():
            try:
                self.show_share_dialog()
            except Exception:
                pass
        self.btn_share_link = Button(
            self.net_ctrl_frame, text="SHARE LINK", command=_open_share_dialog,
            bg='#00A3FF', fg='white', font=('Nirmala UI', 8, 'bold'),
            padx=5, pady=2, relief='flat', cursor='hand2'
        )
        self.btn_share_link.pack(side='left', padx=2)
        
        def _enable_lan_access():
            try:
                self.remote_access_var.set(False)
            except Exception:
                pass
            try:
                # Run firewall fix for current ports
                def _temp_firewall_fix():
                    http_port = getattr(self.web_server, 'port', 8080) if hasattr(self, 'web_server') and self.web_server else 5050
                    https_port = getattr(self.web_server, 'https_port', None) if hasattr(self, 'web_server') and self.web_server else None
                    cmd_http = f'netsh advfirewall firewall add rule name="VocaAI HTTP {http_port}" dir=in action=allow protocol=TCP localport={http_port} profile=any'
                    cmd_https = f'netsh advfirewall firewall add rule name="VocaAI HTTPS {https_port}" dir=in action=allow protocol=TCP localport={https_port} profile=any' if https_port else None
                    try:
                        import subprocess
                        if cmd_https:
                            direct_cmd = cmd_http + " & " + cmd_https
                        else:
                            direct_cmd = cmd_http
                        subprocess.run(["powershell", "-NoProfile", "-Command", direct_cmd], capture_output=True, text=True, shell=False)
                    except Exception:
                        pass
                _temp_firewall_fix()
            except Exception:
                pass
            try:
                # Start local host and show QR
                self.host_network()
                self.root.after(800, lambda: self.show_qr_code(None))
            except Exception:
                pass
            try:
                # Show SSID and IP
                import subprocess, re
                ssid = None
                try:
                    out = subprocess.check_output(["netsh", "wlan", "show", "interfaces"], encoding="utf-8", errors="ignore")
                    m = re.search(r"SSID\s*:\s*(.+)", out)
                    if m:
                        ssid = m.group(1).strip()
                except Exception:
                    ssid = None
                ip = None
                try:
                    if hasattr(self, 'web_server') and self.web_server and hasattr(self.web_server, 'available_ips') and self.web_server.available_ips:
                        ip = self.web_server.available_ips[0]
                except Exception:
                    ip = None
                try:
                    from tkinter import messagebox
                    msg = "LAN Access Enabled"
                    if ssid: msg += f"\nWi-Fi: {ssid}"
                    if ip and hasattr(self, 'web_server') and self.web_server:
                        msg += f"\nIP: http://{ip}:{self.web_server.port}"
                    messagebox.showinfo("LAN Setup", msg, parent=self.root)
                except Exception:
                    pass
            except Exception:
                pass
        
        self.btn_lan = Button(
            self.network_panel, text="Enable LAN Access", command=_enable_lan_access,
            bg='#222', fg='white', font=('Nirmala UI', 8, 'bold'),
            padx=8, pady=2, relief='flat', cursor='hand2'
        )
        self.btn_lan.pack(anchor='w', pady=(4, 0))
        
        # Remote Access (Internet) Checkbox
        has_auth = self.web_server.has_ngrok_auth()
        # Auto-enable if auth is present, or default to True to prompt user
        self.remote_access_var = BooleanVar(value=True) 
        self.chk_remote = Checkbutton(
            self.network_panel, text="Enable Remote Access (Internet)" + (" (Recommended)" if has_auth else ""), variable=self.remote_access_var,
            bg=self.colors['bg_panel'], fg='#00FFD1', selectcolor='#222', activebackground=self.colors['bg_panel'],
            activeforeground='#fff', font=('Nirmala UI', 8, 'bold')
        )
        self.chk_remote.pack(pady=(5, 0), anchor='w')
        
        self.btn_ngrok_setup = Button(
            self.network_panel, text="Set Ngrok Token", command=self.show_ngrok_setup_dialog,
            bg='#444', fg='white', font=('Nirmala UI', 8),
            padx=8, pady=2, relief='flat', cursor='hand2'
        )
        self.btn_ngrok_setup.pack(anchor='w', pady=(4, 0))
        
        self.btn_refresh_ngrok = Button(
            self.network_panel, text="Refresh Internet Link", command=self.refresh_ngrok_tunnel,
            bg='#333', fg='white', font=('Nirmala UI', 8),
            padx=8, pady=2, relief='flat', cursor='hand2', state='disabled'
        )
        self.btn_refresh_ngrok.pack(anchor='w', pady=(4, 0))
        
        # Preferred Hostname (Advanced)
        Label(self.network_panel, text="Preferred Hostname (advanced):", fg='#888', bg=self.colors['bg_panel'], font=('Nirmala UI', 8)).pack(anchor='w', padx=5, pady=(6,0))
        self.hostname_entry = Entry(self.network_panel, bg='#222', fg='white', width=28, relief='flat', font=('Consolas', 10))
        self.hostname_entry.insert(0, "") # Leave empty unless user has reserved hostname
        self.hostname_entry.pack(anchor='w', padx=5, pady=(2,0))
        
        # Force Cloudflare Link Button
        def _force_cloudflare():
            try:
                if hasattr(self, 'web_server') and self.web_server:
                    try:
                        self.remote_link_label.config(text="Internet: Starting Cloudflare...", fg='#888')
                        self.root.update_idletasks()
                    except Exception:
                        pass
                    self.web_server.set_callback(self.on_web_message, self.web_server_log)
                    url = self.web_server.start_cloudflare()
                    if url and "http" in str(url):
                        display_url = url
                        if len(display_url) > 30:
                            display_url = display_url[:15] + "..." + display_url[-10:]
                        self.remote_link_label.config(text=f"Internet: {display_url}", fg='#00A3FF')
                        if hasattr(self, 'btn_copy_link'):
                            self.btn_copy_link.config(state='normal', bg='#444', command=self.copy_remote_link)
                        if hasattr(self, 'btn_whatsapp'):
                            self.btn_whatsapp.config(state='normal', bg='#25D366', command=self.share_whatsapp)
                        if hasattr(self, 'btn_qr'):
                            self.btn_qr.config(state='normal', command=lambda u=url: self.show_qr_code(u))
                        if hasattr(self, 'btn_open_remote'):
                            self.btn_open_remote.config(state='normal', bg='#444')
                        try:
                            import webbrowser
                            self.remote_link_label.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
                        except Exception:
                            pass
                    else:
                        try:
                            # Attempt login once automatically, then retry
                            ok = self.web_server.cloudflare_login()
                            from tkinter import messagebox
                            if ok:
                                messagebox.showinfo("Cloudflare", "Browser login started. Complete login, then click OK to continue.", parent=self.root)
                                url2 = self.web_server.start_cloudflare()
                                if url2 and "http" in str(url2):
                                    display_url = url2 if len(url2) <= 30 else (url2[:15] + "..." + url2[-10:])
                                    self.remote_link_label.config(text=f"Internet: {display_url}", fg='#00A3FF')
                                    if hasattr(self, 'btn_copy_link'):
                                        self.btn_copy_link.config(state='normal', bg='#444', command=self.copy_remote_link)
                                    if hasattr(self, 'btn_whatsapp'):
                                        self.btn_whatsapp.config(state='normal', bg='#25D366', command=self.share_whatsapp)
                                    if hasattr(self, 'btn_qr'):
                                        self.btn_qr.config(state='normal', command=lambda u=url2: self.show_qr_code(u))
                                    if hasattr(self, 'btn_open_remote'):
                                        self.btn_open_remote.config(state='normal', bg='#444')
                                    try:
                                        import webbrowser
                                        self.remote_link_label.bind("<Button-1>", lambda e, u=url2: webbrowser.open(u))
                                    except Exception:
                                        pass
                                    return
                        except Exception:
                            pass
                        # Final fallback: show error guidance
                        try:
                            from tkinter import messagebox
                        except Exception:
                            messagebox = None
                        err = getattr(self.web_server, 'cfd_error', None)
                        if err:
                            message = f"Cloudflare link could not be created.\n\nDetails: {err}\n\nTry 'Cloudflare Login', then 'Use Cloudflare Link' again."
                        else:
                            message = "Cloudflare link could not be created.\nTry 'Cloudflare Login', then 'Use Cloudflare Link' again."
                        try:
                            if messagebox:
                                messagebox.showerror("Cloudflare", message, parent=self.root)
                        except Exception:
                            pass
                        self.remote_link_label.config(text="Internet: Not reachable", fg='red')
            except Exception:
                self.remote_link_label.config(text="Internet: Not reachable", fg='red')
        self.btn_force_cfd = Button(
            self.network_panel, text="Use Cloudflare Link", command=_force_cloudflare,
            bg='#333', fg='white', font=('Nirmala UI', 8),
            padx=8, pady=2, relief='flat', cursor='hand2'
        )
        self.btn_force_cfd.pack(anchor='w', pady=(4, 0))
        
        # (VPN link option removed per request)
        
        # Persistent Cloudflare Link
        def _set_persistent_cfd():
            try:
                from tkinter import simpledialog, messagebox
                host = simpledialog.askstring("Persistent Cloudflare Link", "Enter your hostname (e.g., app.example.com or name.yourdomain.com):", parent=self.root)
                if not host:
                    return
                if hasattr(self, 'web_server') and self.web_server:
                    self.web_server.set_callback(self.on_web_message, self.web_server_log)
                    url = self.web_server.start_cloudflare_named(host.strip())
                    if url and "http" in str(url):
                        display_url = url if len(url) <= 30 else (url[:15] + "..." + url[-10:])
                        self.remote_link_label.config(text=f"Internet: {display_url}", fg='#00A3FF')
                        if hasattr(self, 'btn_copy_link'):
                            self.btn_copy_link.config(state='normal', bg='#444', command=self.copy_remote_link)
                        if hasattr(self, 'btn_whatsapp'):
                            self.btn_whatsapp.config(state='normal', bg='#25D366', command=self.share_whatsapp)
                        if hasattr(self, 'btn_qr'):
                            self.btn_qr.config(state='normal', command=lambda u=url: self.show_qr_code(u))
                        if hasattr(self, 'btn_open_remote'):
                            self.btn_open_remote.config(state='normal', bg='#444')
                    else:
                        messagebox.showwarning("Persistent Link", "Could not create the persistent link.\nYou may need to log in when prompted and ensure the hostname is in your Cloudflare zone.", parent=self.root)
            except Exception:
                pass
        self.btn_persist_cfd = Button(
            self.network_panel, text="Set Persistent Link (Cloudflare)", command=_set_persistent_cfd,
            bg='#333', fg='white', font=('Nirmala UI', 8),
            padx=8, pady=2, relief='flat', cursor='hand2'
        )
        self.btn_persist_cfd.pack(anchor='w', pady=(4, 0))
        
        # Cloudflare Login
        def _cloudflare_login():
            try:
                if hasattr(self, 'web_server') and self.web_server:
                    ok = self.web_server.cloudflare_login()
                    from tkinter import messagebox
                    if ok:
                        messagebox.showinfo("Cloudflare", "A browser window may open to log in.\nComplete the login, then use 'Set Persistent Link (Cloudflare)'.", parent=self.root)
                    else:
                        messagebox.showerror("Cloudflare", "Could not start Cloudflare login.", parent=self.root)
            except Exception:
                pass
        self.btn_cfd_login = Button(
            self.network_panel, text="Cloudflare Login", command=_cloudflare_login,
            bg='#333', fg='white', font=('Nirmala UI', 8),
            padx=8, pady=2, relief='flat', cursor='hand2'
        )
        self.btn_cfd_login.pack(anchor='w', pady=(4, 0))
        
        def _public_ip_guide():
            try:
                import urllib.request
                public_ip = None
                try:
                    with urllib.request.urlopen("https://api.ipify.org?format=text", timeout=5) as resp:
                        public_ip = resp.read().decode("utf-8").strip()
                except Exception:
                    public_ip = None
                port = None
                scheme = "http"
                try:
                    if hasattr(self, 'web_server') and self.web_server:
                        if getattr(self.web_server, 'https_port', None) and getattr(self.web_server, 'https_server', None):
                            port = self.web_server.https_port
                            scheme = "https"
                        else:
                            port = self.web_server.port
                    else:
                        port = 5050
                except Exception:
                    port = 5050
                from tkinter import Toplevel, Label, Button, Entry, messagebox
                dlg = Toplevel(self.root)
                dlg.title("Public IP Link (Guide)")
                dlg.geometry("460x220")
                dlg.configure(bg='#1e1e1e')
                link = None
                if public_ip and port:
                    link = f"{scheme}://{public_ip}:{port}"
                Label(dlg, text="Step 1: Configure port forwarding on your router.", fg='white', bg='#1e1e1e', font=('Arial', 10, 'bold')).pack(pady=(10, 4))
                Label(dlg, text="Forward external port to this PC's local port. Then share the link below.", fg='#ccc', bg='#1e1e1e', font=('Arial', 9)).pack()
                Label(dlg, text="Public Link:", fg='white', bg='#1e1e1e', font=('Arial', 10, 'bold')).pack(pady=(10, 4))
                entry = Entry(dlg, width=60, font=('Consolas', 10))
                entry.pack(padx=10)
                entry.delete(0, 'end')
                entry.insert(0, link if link else "Unavailable")
                def _copy():
                    try:
                        if link:
                            self.root.clipboard_clear()
                            self.root.clipboard_append(link)
                    except Exception:
                        pass
                def _open():
                    try:
                        if link:
                            import webbrowser
                            webbrowser.open(link)
                    except Exception:
                        pass
                btn_frame = Frame(dlg, bg='#1e1e1e')
                btn_frame.pack(pady=10)
                Button(btn_frame, text="Copy", command=_copy, bg='#444', fg='white', padx=10, pady=4).pack(side='left', padx=4)
                Button(btn_frame, text="Open", command=_open, bg='#444', fg='white', padx=10, pady=4).pack(side='left', padx=4)
                Button(dlg, text="Close", command=dlg.destroy, bg='#333', fg='white').pack(pady=(0,10))
            except Exception:
                from tkinter import messagebox
                messagebox.showerror("Error", "Could not prepare public IP link guide.", parent=self.root)
        self.btn_public_ip = Button(
            self.network_panel, text="Public IP (Guide)", command=_public_ip_guide,
            bg='#333', fg='white', font=('Nirmala UI', 8),
            padx=8, pady=2, relief='flat', cursor='hand2'
        )
        self.btn_public_ip.pack(anchor='w', pady=(4, 0))
        
        def _auto_public_upnp():
            try:
                if hasattr(self, 'web_server') and self.web_server:
                    self.web_server.set_callback(self.on_web_message, self.web_server_log)
                    url = self.web_server.try_upnp_public()
                    if url and "http" in str(url):
                        display_url = url if len(url) <= 30 else (url[:15] + "..." + url[-10:])
                        self.remote_link_label.config(text=f"Public IP: {display_url}", fg='#00A3FF')
                        if hasattr(self, 'btn_copy_link'):
                            self.btn_copy_link.config(state='normal', bg='#444', command=self.copy_remote_link)
                        if hasattr(self, 'btn_whatsapp'):
                            self.btn_whatsapp.config(state='normal', bg='#25D366', command=self.share_whatsapp)
                        if hasattr(self, 'btn_qr'):
                            self.btn_qr.config(state='normal', command=lambda u=url: self.show_qr_code(u))
                        if hasattr(self, 'btn_open_remote'):
                            self.btn_open_remote.config(state='normal', bg='#444')
                        try:
                            import webbrowser
                            self.remote_link_label.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
                        except Exception:
                            pass
                    else:
                        from tkinter import messagebox
                        messagebox.showwarning("UPnP", "Could not set up automatic port forwarding. Use 'Public IP (Guide)' for manual port forwarding.", parent=self.root)
            except Exception:
                from tkinter import messagebox
                messagebox.showerror("UPnP", "Automatic port forwarding failed.", parent=self.root)
        self.btn_public_upnp = Button(
            self.network_panel, text="Public IP (Auto Port Forward)", command=_auto_public_upnp,
            bg='#333', fg='white', font=('Nirmala UI', 8),
            padx=8, pady=2, relief='flat', cursor='hand2'
        )
        self.btn_public_upnp.pack(anchor='w', pady=(4, 0))

        def _diagnose_remote():
            try:
                self.remote_link_label.config(text="Internet: Checking...", fg='#00A3FF')
                self.root.update()
                if hasattr(self, 'web_server') and self.web_server:
                    try:
                        self.web_server.set_callback(self.on_web_message, self.web_server_log)
                    except Exception:
                        pass
                    url = self.web_server.start(use_ngrok=True)
                    if url == "AUTH_REQUIRED":
                        self.remote_link_label.config(text="Status: MISSING AUTH TOKEN", fg='red')
                        if not self.ngrok_prompt_shown:
                            self.ngrok_prompt_shown = True
                            self.show_ngrok_setup_dialog()
                        return
                    if url and "http" in str(url):
                        display_url = url
                        if len(display_url) > 30:
                            display_url = display_url[:15] + "..." + display_url[-10:]
                        import urllib.request, ssl
                        test_url = str(url).rstrip('/') + '/ping'
                        reachable = False
                        try:
                            if test_url.startswith("https://"):
                                ctx = ssl._create_unverified_context()
                                urllib.request.urlopen(test_url, timeout=4, context=ctx)
                            else:
                                urllib.request.urlopen(test_url, timeout=4)
                            reachable = True
                        except Exception:
                            reachable = False
                        if reachable:
                            self.remote_link_label.config(text=f"Internet: {display_url}", fg='#00A3FF')
                            if hasattr(self, 'btn_copy_link'):
                                self.btn_copy_link.config(state='normal', bg='#444', command=self.copy_remote_link)
                            if hasattr(self, 'btn_whatsapp'):
                                self.btn_whatsapp.config(state='normal', bg='#25D366', command=self.share_whatsapp)
                            if hasattr(self, 'btn_qr'):
                                self.btn_qr.config(state='normal', command=lambda u=url: self.show_qr_code(u))
                            if hasattr(self, 'btn_open_remote'):
                                self.btn_open_remote.config(state='normal', bg='#444')
                            try:
                                import webbrowser
                                self.remote_link_label.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
                            except Exception:
                                pass
                        else:
                            # Auto-fallback to Cloudflare quick tunnel
                            try:
                                url_cf = self.web_server.start_cloudflare()
                            except Exception:
                                url_cf = None
                            if url_cf and "http" in str(url_cf):
                                display_cf = url_cf
                                if len(display_cf) > 30:
                                    display_cf = display_cf[:15] + "..." + display_cf[-10:]
                                try:
                                    cf_test = str(url_cf).rstrip('/') + '/ping'
                                    ok = False
                                    try:
                                        if cf_test.startswith("https://"):
                                            ctx2 = ssl._create_unverified_context()
                                            urllib.request.urlopen(cf_test, timeout=5, context=ctx2)
                                        else:
                                            urllib.request.urlopen(cf_test, timeout=5)
                                        ok = True
                                    except Exception:
                                        ok = False
                                    if ok:
                                        self.remote_link_label.config(text=f"Internet: {display_cf}", fg='#00A3FF')
                                        if hasattr(self, 'btn_copy_link'):
                                            self.btn_copy_link.config(state='normal', bg='#444', command=self.copy_remote_link)
                                        if hasattr(self, 'btn_whatsapp'):
                                            self.btn_whatsapp.config(state='normal', bg='#25D366', command=self.share_whatsapp)
                                        if hasattr(self, 'btn_qr'):
                                            self.btn_qr.config(state='normal', command=lambda u=url_cf: self.show_qr_code(u))
                                        if hasattr(self, 'btn_open_remote'):
                                            self.btn_open_remote.config(state='normal', bg='#444')
                                        try:
                                            import webbrowser
                                            self.remote_link_label.bind("<Button-1>", lambda e, u=url_cf: webbrowser.open(u))
                                        except Exception:
                                            pass
                                    else:
                                        self.remote_link_label.config(text="Internet: Not reachable", fg='red')
                                except Exception:
                                    self.remote_link_label.config(text="Internet: Not reachable", fg='red')
                            else:
                                self.remote_link_label.config(text="Internet: Not reachable", fg='red')
                    else:
                        self.remote_link_label.config(text="Internet: Disabled", fg='#00A3FF')
            except Exception:
                pass
        self.btn_check_remote = Button(
            self.network_panel, text="Check Remote Connectivity", command=_diagnose_remote,
            bg='#333', fg='white', font=('Nirmala UI', 8),
            padx=8, pady=2, relief='flat', cursor='hand2'
        )
        self.btn_check_remote.pack(anchor='w', pady=(4, 0))

        # Add Help/Status Button
        self.btn_help = Button(
            self.network_panel, text="Help / Status", command=self.show_network_help,
            bg='#333', fg='white', font=('Nirmala UI', 7),
            padx=5, pady=1, relief='flat', cursor='hand2'
        )
        self.btn_help.pack(anchor='e', pady=(0, 5))
        
        # Links Display Area
        self.mobile_link_frame = Frame(self.network_panel, bg=self.colors['bg_panel'])
        self.mobile_link_frame.pack(pady=(5, 0), fill='x')
        
        # Local Link
        self.local_link_label = Label(
            self.mobile_link_frame, text="Home Wi-Fi: Offline", font=('Consolas', 9),
            fg='#888', bg=self.colors['bg_panel'], cursor="hand2", anchor='w'
        )
        self.local_link_label.pack(fill='x', pady=2)
        
        # Remote Link
        self.remote_link_label = Label(
            self.mobile_link_frame, text="Internet: Disabled", font=('Consolas', 9, 'bold'),
            fg='#00A3FF', bg=self.colors['bg_panel'], cursor="hand2", anchor='w'
        )
        self.remote_link_label.pack(fill='x', pady=2)
        
        # Mobile Link Label (Legacy support)
        self.mobile_link_label = Label(self.network_panel, text="", bg='#1e1e1e', fg='#888', font=("Arial", 1))
        
        # Sharing Buttons Frame
        self.share_frame = Frame(self.network_panel, bg=self.colors['bg_panel'])
        self.share_frame.pack(fill='x', pady=5)
        
        # Copy Button
        self.btn_copy_link = Button(
            self.share_frame, text="📋 Copy", command=self.copy_remote_link,
            bg='#333', fg='white', font=('Nirmala UI', 8),
            padx=10, pady=2, relief='flat', cursor='hand2', state='disabled'
        )
        self.btn_copy_link.pack(side='left', fill='x', expand=True, padx=(0, 2))
        
        # WhatsApp Button
        self.btn_whatsapp = Button(
            self.share_frame, text="💬 WhatsApp", command=self.share_whatsapp,
            bg='#25D366', fg='white', font=('Nirmala UI', 8, 'bold'),
            padx=10, pady=2, relief='flat', cursor='hand2', state='disabled'
        )
        self.btn_whatsapp.pack(side='left', fill='x', expand=True, padx=(2, 0))
        
        # QR Code Button (New)
        self.btn_qr = Button(
            self.share_frame, text="📱 QR", command=lambda: self.show_qr_code(None),
            bg='#444', fg='white', font=('Nirmala UI', 8),
            padx=10, pady=2, relief='flat', cursor='hand2', state='normal'
        )
        self.btn_qr.pack(side='left', fill='x', expand=True, padx=(2, 0))
        
        # Open Remote Link Button
        def _open_remote_link():
            try:
                import webbrowser
                url = None
                if hasattr(self, 'web_server') and self.web_server:
                    if self.web_server.public_url and "http" in str(self.web_server.public_url):
                        url = self.web_server.public_url
                    elif self.web_server.local_url:
                        url = self.web_server.local_url
                if not url and hasattr(self, 'web_url'):
                    url = self.web_url
                if url:
                    webbrowser.open(url)
            except Exception:
                pass
        self.btn_open_remote = Button(
            self.share_frame, text="🔗 Open", command=_open_remote_link,
            bg='#444', fg='white', font=('Nirmala UI', 8),
            padx=10, pady=2, relief='flat', cursor='hand2', state='disabled'
        )
        self.btn_open_remote.pack(side='left', fill='x', expand=True, padx=(2, 0))
        
        def quick_remote_link():
            try:
                self.remote_access_var.set(True)
                self.refresh_ngrok_tunnel()
                if hasattr(self, 'web_server') and self.web_server and self.web_server.public_url and "http" in self.web_server.public_url:
                    self.show_qr_code(self.web_server.public_url)
                    try:
                        import webbrowser
                        webbrowser.open(self.web_server.public_url)
                    except Exception:
                        pass
            except Exception:
                pass
        
        self.btn_quick_remote = Button(
            self.network_panel, text="Invite Anyone", command=quick_remote_link,
            bg='#00A3FF', fg='white', font=('Nirmala UI', 8, 'bold'),
            padx=8, pady=2, relief='flat', cursor='hand2'
        )
        self.btn_quick_remote.pack(anchor='w', pady=(4, 0))
        
        # Keep old label for compatibility but hidden or repurposed
        self.mobile_link_label = Label(self.mobile_link_frame, text="", bg=self.colors['bg_panel'])
        # self.mobile_link_label.pack() # Don't pack it to hide it
        
        # Language Selection (Moved below Network)
        self.lang_frame = Frame(self.sidebar, bg=self.colors['bg_panel'])
        self.lang_frame.pack(fill='x', pady=5)
        
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
        
        # NEW: Multi-Language Translation Dropdown
        if self.translator:
            self.translation_frame = Frame(self.sidebar, bg=self.colors['bg_panel'])
            self.translation_frame.pack(fill='x', pady=5)
            
            Label(self.translation_frame, text="TRANSLATE TO:", font=('Nirmala UI', 8, 'bold'),
                  fg=self.colors['text_dim'], bg=self.colors['bg_panel']).pack(anchor='w', padx=5)
            
            self.translation_var = StringVar()
            self.translation_var.set("English")  # Default
            self.translation_combo = ttk.Combobox(
                self.translation_frame, textvariable=self.translation_var, 
                values=self.translator.get_language_options(), state="readonly",
                font=('Nirmala UI', 9), width=15
            )
            self.translation_combo.pack(fill='x', padx=5, pady=2)
            self.translation_combo.bind("<ComboboxSelected>", self.on_translation_language_change)
            
            # Teach Me Mode Toggle
            self.teach_mode_var = BooleanVar(value=False)
            self.teach_mode_btn = Checkbutton(
                self.translation_frame, text="🧠 Teach Me Mode", variable=self.teach_mode_var,
                command=self.toggle_teach_mode, font=('Nirmala UI', 9, 'bold'),
                bg=self.colors['bg_panel'], fg='#FFD700', selectcolor='#222',
                activebackground=self.colors['bg_panel'], activeforeground='#FFD700'
            )
            self.teach_mode_btn.pack(anchor='w', padx=5, pady=(10, 0))
        
        # Skeleton View (Moved below Language)
        self.skeleton_title = Label(
            self.sidebar, text="LIVE SKELETON TRACKING", font=('Nirmala UI', 10, 'bold'),
            fg=self.colors['text_dim'], bg=self.colors['bg_panel']
        )
        self.skeleton_title.pack(pady=(10, 0))
        
        self.skeleton_canvas = Canvas(self.sidebar, bg='black', width=300, height=200, highlightthickness=1, highlightbackground='#222')
        self.skeleton_canvas.pack(pady=5)
        

        
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
        
        # Auto-Speak Toggle (Text-to-Speech)
        self.auto_speak_var = BooleanVar(value=True)
        self.chk_autospeak = Checkbutton(
            self.sidebar, text="Auto-Speak (TTS)", variable=self.auto_speak_var,
            bg=self.colors['bg_panel'], fg='white', selectcolor='#222', activebackground='#333',
            font=('Arial', 9)
        )
        self.chk_autospeak.pack(pady=5)
        
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
        self.last_gesture_time = 0 # Thumbs up cooldown
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
            },
            'PAIN': {
                'en': "Make a fist and press it gently on your chest to show pain.",
                'ml': "വേദനയുള്ള ഭാഗത്ത് മുഷ്ടി വെച്ച് അല്പം ഞെക്കുക."
            },
            'HUNGRY': {
                'en': "Place your open hand on your upper stomach and move it down slightly.",
                'ml': "തടിച്ച ഉള്ളംകൈ വയറ്റിന് മുകളിൽ വച്ച് താഴേക്ക് അല്പം നീക്കുക."
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
        
        # Load existing history from database
        self.load_history_from_db()
        
        # AUTO-START: Use a reliable, non-blocking timer to start the web server
        threading.Timer(0.5, self.host_network).start()

        # Start a poller for the web server status queue
        self.root.after(100, self.poll_web_server_queue)

    def poll_web_server_queue(self):
        try:
            status, data = self.web_server_status_queue.get_nowait()
            self.on_web_server_status(status, data)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.poll_web_server_queue)

    def on_web_server_status(self, status, data):
        """Thread-safe method to update UI based on web server status. Restores connection between web server and main app."""
        if status == "RUNNING":
            # Bind main app to the manager's running server (connection: mobile -> server -> main app)
            server = self.web_server_manager.get_server_instance()
            if server:
                self.web_server = server
                self.web_server.set_callback(self.on_web_message, self.web_server_log)
                print("Web server connected: callbacks set for mobile messages.")
            self.web_url = data.get("url")
            local_url = data.get("local_url")
            public_url = data.get("public_url")
            ngrok_error = data.get("ngrok_error")
            cfd_url = data.get("cfd_url")
            cfd_error = data.get("cfd_error")

            if local_url:
                self.local_link_label.config(text=f"Home Wi-Fi: {local_url} (Click for Options)")
            if public_url or cfd_url:
                if not public_url and cfd_url:
                    public_url = cfd_url
                if public_url == "AUTH_REQUIRED":
                    self.remote_link_label.config(text="Status: MISSING AUTH TOKEN", fg='red')
                    if not self.ngrok_prompt_shown:
                        self.ngrok_prompt_shown = True
                        self.show_ngrok_setup_dialog()
                else:
                    self.remote_link_label.config(text=f"Internet: {public_url}", fg='#00A3FF')
                    try:
                        import webbrowser
                        self.remote_link_label.bind("<Button-1>", lambda e, u=public_url: webbrowser.open(u))
                    except Exception:
                        pass
            elif ngrok_error or cfd_error:
                self.remote_link_label.config(text="Internet: Not reachable", fg='red')

            # Enable share buttons once any usable URL is available
            best_url = None
            if public_url and "http" in public_url:
                best_url = public_url
            elif local_url:
                best_url = local_url
            if best_url:
                if hasattr(self, 'btn_copy_link'):
                    self.btn_copy_link.config(state='normal', bg='#444', command=self.copy_remote_link)
                if hasattr(self, 'btn_whatsapp'):
                    self.btn_whatsapp.config(state='normal', bg='#25D366', command=self.share_whatsapp)
                if hasattr(self, 'btn_qr'):
                    self.btn_qr.config(state='normal', command=lambda u=best_url: self.show_qr_code(u))
                if hasattr(self, 'btn_open_remote'):
                    self.btn_open_remote.config(state='normal', bg='#444')
                # Auto-open share dialog the first time a URL becomes available
                try:
                    if not hasattr(self, 'share_dialog_auto_opened') or not self.share_dialog_auto_opened:
                        self.share_dialog_auto_opened = True
                        self.show_share_dialog()
                except Exception:
                    pass
            
            self.btn_host.config(state='disabled', bg='#222')
            self.chk_remote.config(state='disabled')

        elif status == "ERROR":
            from tkinter import messagebox
            messagebox.showerror("Web Server Error", data.get("message", "An unknown error occurred."))
            self.reset_network()

        elif status == "STOPPED":
            self.reset_network()

    def load_history_from_db(self):
        """Load recent history from database into the listbox"""
        try:
            # Get last 20 entries (Newest -> Oldest)
            history = self.db.get_recent_history(20)
            
            # Insert them in reverse order (Oldest -> Newest) so the Newest ends up at the top
            for item in reversed(history): 
                # item is (event_type, content, formatted_time)
                event_type, content, time_str = item
                try:
                    # Extract HH:MM from time_str (YYYY-MM-DD HH:MM:SS)
                    short_time = time_str.split(' ')[1][:5]
                except:
                    short_time = "00:00"
                
                entry = f"[{short_time}] {content}"
                self.log_list.insert(0, entry)
                
            print(f"Loaded {len(history)} history entries from database.")
        except Exception as e:
            print(f"Error loading history: {e}")

    def show_mic_selector(self):
        """Show dialog to select microphone"""
        try:
            mics = self.voice_recognizer.get_available_microphones()
            if not mics:
                from tkinter import messagebox
                messagebox.showerror("Error", "No microphones found!")
                return
                
            # Create dialog
            dialog = Toplevel(self.root)
            dialog.title("Select Microphone")
            dialog.geometry("400x150")
            dialog.configure(bg='#1e1e1e')
            dialog.transient(self.root)
            dialog.grab_set()
            
            Label(dialog, text="Select Input Device:", fg='white', bg='#1e1e1e', font=('Arial', 10)).pack(pady=10)
            
            # Combobox
            mic_var = StringVar()
            combo = ttk.Combobox(dialog, textvariable=mic_var, state="readonly", width=40)
            combo['values'] = [f"{i}: {name}" for i, name in mics]
            
            # Set current if known
            current_idx = self.voice_recognizer.device_index
            if current_idx is not None:
                # Find matching index in list
                for j, (idx, name) in enumerate(mics):
                    if idx == current_idx:
                        combo.current(j)
                        break
            else:
                if len(mics) > 0:
                    combo.current(0)
                
            combo.pack(pady=5)
            
            def on_select():
                selection = combo.get()
                if selection:
                    idx = int(selection.split(':')[0])
                    print(f"User selected mic index: {idx}")
                    self.voice_recognizer.set_device(idx)
                    self.restart_mic()
                    dialog.destroy()
            
            Button(dialog, text="Use Selected Device", command=on_select,
                   bg='#0078D4', fg='white', padx=10, pady=5).pack(pady=10)
                   
        except Exception as e:
            print(f"Error showing mic selector: {e}")

    def restart_mic(self):
        """Manually restart the voice recognizer"""
        print("App: Manual Mic Restart triggered...")
        # Force re-initialization of microphone
        self.voice_recognizer.set_device(self.voice_recognizer.device_index)
        self.status_var.set("RESTARTING MIC...")
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

    def on_translation_language_change(self, event=None):
        """Handle translation language selection change"""
        if not self.translator:
            return
            
        selected_language = self.translation_var.get()
        language_code = self.translator.SUPPORTED_LANGUAGES.get(selected_language)
        
        if language_code:
            success = self.translator.set_language(language_code)
            if success:
                print(f"Translation target set to: {selected_language} ({language_code})")
                # Update UI to show current translation target
                self.status_var.set(f"Translating to: {selected_language}")
                self.root.after(3000, lambda: self.status_var.set(""))
            else:
                print(f"Failed to set translation language: {selected_language}")

    def toggle_teach_mode(self):
        """Toggle Teach Me mode for sign language learning"""
        self.teach_mode_active = self.teach_mode_var.get()
        
        if self.teach_mode_active:
            print("Teach Me Mode: ACTIVATED")
            self.status_var.set("🧠 TEACH ME MODE: ACTIVE")
            # Change UI color to indicate teaching mode
            self.translation_panel.config(fg='#FFD700')  # Gold color for teaching mode
            self.teach_mode_btn.config(fg='#FFD700')
        else:
            print("Teach Me Mode: DEACTIVATED")
            self.status_var.set("")
            # Revert UI color
            self.translation_panel.config(fg='#00FFD1')  # Back to cyan
            self.teach_mode_btn.config(fg='#FFD700')

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
        
        # Save to database
        self.db.add_entry("VOICE", text, self.current_lang)
        
        # Send to Network
        if hasattr(self, 'network'):
            self.network.send_message("VOICE", text)
            
        # Send to Web
        if hasattr(self, 'web_server') and self.web_server.running:
            self.web_server.broadcast_update("VOICE", text)
        
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
    
    def update_dashboard_data(self, confidence_val=0, new_sentence=None):
        """Update the bottom dashboard with real-time stats"""
        try:
            # 1. Update Session Log
            if new_sentence:
                timestamp = time.strftime("%H:%M:%S")
                self.log_list.insert(0, f"[{timestamp}] {new_sentence}")
                # Keep log manageable
                if self.log_list.size() > 50:
                    self.log_list.delete(50, tk.END)

            # 2. Update CPU/Memory (Removed as per user request)
            
            # 3. Update Graph (Shift and Draw)
            if hasattr(self, 'metrics_canvas'):
                # Shift everything left
                self.metrics_canvas.move("graph_line", -5, 0)
                
                # Calculate new point
                h = 150
                y = h - (confidence_val * h)
                x = 250
                
                # Initialize last point if needed
                if not hasattr(self, 'last_graph_y'):
                    self.last_graph_y = h
                
                # Draw line segment
                self.metrics_canvas.create_line(x-5, self.last_graph_y, x, y, 
                                              fill='#00FFD1', width=2, tags="graph_line")
                self.last_graph_y = y
                
                # Cleanup off-screen items occasionally
                if int(time.time()) % 10 == 0:
                    # Clear old lines if too many accumulate
                    items = self.metrics_canvas.find_withtag("graph_line")
                    if len(items) > 500:
                        self.metrics_canvas.delete("graph_line")
                        self.last_graph_y = h # Reset graph start point

        except Exception as e:
            pass # Fail silently to not disrupt main loop

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

            # Check for HUNGRY
            elif hasattr(self.sign_detector, 'detect_hungry') and self.sign_detector.detect_hungry(
                landmarks['left_hand'] if landmarks['left_hand'] else landmarks['right_hand'],
                landmarks['pose']
            ):
                detected_sign = "HUNGRY"
                
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

            # Check for PAIN
            elif hasattr(self.sign_detector, 'detect_pain') and self.sign_detector.detect_pain(
                landmarks['left_hand'] if landmarks['left_hand'] else landmarks['right_hand'],
                landmarks['pose']
            ):
                detected_sign = "PAIN"
            
            # Check for MEDICINE
            elif self.sign_detector.detect_medicine(
                landmarks['left_hand'] if landmarks['left_hand'] else landmarks['right_hand'],
                landmarks['face']
            ):
                detected_sign = "MEDICINE"
            
            # Check for WASHROOM - Using placeholder check as method not in snippet but referenced
            # Assuming it exists in backend or needs implementation
            elif hasattr(self.sign_detector, 'detect_washroom') and self.sign_detector.detect_washroom(
                landmarks['left_hand'] if landmarks['left_hand'] else landmarks['right_hand']
            ):
                detected_sign = "WASHROOM"
            
            # Check for WHERE
            elif hasattr(self.sign_detector, 'detect_where') and self.sign_detector.detect_where(
                landmarks['left_hand'] if landmarks['left_hand'] else landmarks['right_hand']
            ):
                detected_sign = "WHERE"
            
            # Add sign to buffer if detected
            if detected_sign:
                self.sentence_buffer.add_sign(detected_sign)
                
                # Trigger Emergency SOS Mode
                if detected_sign == "EMERGENCY":
                    self.trigger_emergency_sos()
            
            # Check for THUMBS UP (Speak Command)
            current_time = time.time()
            final_sentence = None # Track finalized sentence for dashboard

            if current_time - self.last_gesture_time > 2.0:
                if (landmarks['left_hand'] and self.sign_detector.is_thumbs_up(landmarks['left_hand'])) or \
                   (landmarks['right_hand'] and self.sign_detector.is_thumbs_up(landmarks['right_hand'])):
                    self.last_gesture_time = current_time
                    self.gesture_status = "THUMBS UP: SPEAKING..."
                    # Force speak (finalize current or repeat last)
                    result = self.sentence_buffer.finalize_sentence(speak=True)
                    if result:
                        final_sentence = result
                    else:
                        self.sentence_buffer.speak_last_sentence()
                        
                    self.root.after(2000, lambda: setattr(self, 'gesture_status', ""))

            # Check for idle state (hands dropped or still)
            if not landmarks['left_hand'] and not landmarks['right_hand']:
                if self.sentence_buffer.check_idle():
                    res = self.sentence_buffer.finalize_sentence(speak=self.auto_speak_var.get())
                    if res: final_sentence = res
            elif not self.sign_detector.trajectory_analyzer.is_moving(threshold=0.005, frames=10):
                if self.sentence_buffer.check_idle():
                    res = self.sentence_buffer.finalize_sentence(speak=self.auto_speak_var.get())
                    if res: final_sentence = res
            
            # Update Dashboard with real-time metrics
            _, current_conf = self.sentence_buffer.get_potential_sign()
            self.update_dashboard_data(confidence_val=current_conf, new_sentence=final_sentence)

            # SHOW TRANSLATED SENTENCE ON SCREEN (SUBTITLES)
            if final_sentence:
                 self.voice_text = f"YOU: {final_sentence}"
                 self.voice_text_timer = time.time() + 8 # Show for 8 seconds
                 self.last_voice_captured = final_sentence

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

            # 3.5 Gesture Feedback
            if hasattr(self, 'gesture_status') and self.gesture_status:
                cv2.putText(annotated_frame, self.gesture_status, (w - 350, 58), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

            # 4. Main Result HUD (Bottom Center)
            current_sign = self.sentence_buffer.get_current_display_text() if hasattr(self.sentence_buffer, 'get_current_display_text') else self.sentence_buffer.get_potential_sign()[0]
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
            # Draw error on frame so user can see it
            err_frame = frame.copy()
            cv2.putText(err_frame, f"ERROR: {str(e)[:50]}", (50, 50), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            cv2.putText(err_frame, "Check console for details", (50, 80), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 1)
            return err_frame
            
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
                    _playsnd(sound_file)
                except:
                    break
        else:
            # High-Quality Synthesized Siren Fallback
            while self.sos_sound_running and self.emergency_mode:
                try:
                    # 1. European "Hi-Lo" (2 seconds)
                    for _ in range(2):
                        if not self.sos_sound_running: break
                        _beep(960, 500)
                        if not self.sos_sound_running: break
                        _beep(720, 500)
                    
                    # 2. Rapid "Phaser" (1 second)
                    for _ in range(10):
                        if not self.sos_sound_running: break
                        for f in range(800, 1600, 200):
                            _beep(f, 20)
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

    def append_log(self, message):
        try:
            ts = time.strftime("%H:%M:%S")
            txt = f"[{ts}] {message}"
            self.log_list.insert(0, txt)
            if self.log_list.size() > 200:
                self.log_list.delete(200, 'end')
        except Exception as e:
            try:
                print(f"LOG: {message}")
            except Exception:
                pass
    def show_ngrok_setup_dialog(self):
        """Show the dialog to setup Ngrok authtoken"""
        from tkinter import messagebox, Toplevel, Label, Button, Entry
        import webbrowser
        import subprocess
        
        # Create a custom dialog for token entry
        dialog = Toplevel(self.root)
        dialog.title("Ngrok Setup Required")
        dialog.geometry("500x380")
        dialog.configure(bg='#1e1e1e')
        
        # Make it modal
        dialog.transient(self.root)
        dialog.grab_set()
        
        Label(dialog, text="Remote Access Setup", 
              font=("Arial", 14, "bold"), fg="white", bg="#1e1e1e").pack(pady=(20, 10))
        
        Label(dialog, text="To use the Internet Link, you need a free Ngrok Authtoken.\nThis ensures your connection is secure.", 
              justify="center", fg="#ccc", bg="#1e1e1e", font=("Arial", 10)).pack(pady=5)
              
        # Step 1
        step1_frame = Frame(dialog, bg='#1e1e1e')
        step1_frame.pack(fill='x', padx=20, pady=10)
        
        Button(step1_frame, text="1. Click here to get your Free Token", 
               command=lambda: webbrowser.open("https://dashboard.ngrok.com/get-started/your-authtoken"),
               bg='#25D366', fg='white', font=("Arial", 10, "bold"), padx=10, pady=8, cursor="hand2").pack(fill='x')
        
        # Step 2
        Label(dialog, text="2. Copy the token from the website and paste it below:", 
              justify="left", fg="#ccc", bg="#1e1e1e").pack(pady=(10, 5))
        
        token_entry = Entry(dialog, width=50, font=("Consolas", 10))
        token_entry.pack(pady=5)
        token_entry.focus()
        
        # Error Label
        error_label = Label(dialog, text="", fg="#ff5252", bg="#1e1e1e", font=("Arial", 9))
        error_label.pack(pady=5)
        
        def save_token():
            token = token_entry.get().strip()
            if not token:
                error_label.config(text="Please paste the token first.")
                return
            # Normalize common paste formats
            try:
                s = token.replace("\n", " ").strip()
                # If user pasted full command, extract the last piece
                if "authtoken" in s.lower():
                    parts = [p for p in s.split(" ") if p.strip()]
                    token = parts[-1]
                # Strip quotes
                token = token.strip().strip("'").strip('\"')
            except Exception:
                pass
                
            try:
                # Robustly find ngrok executable
                import os
                # Also prepare runtime auth for pyngrok
                try:
                    from pyngrok import conf as _py_conf
                    default_conf = _py_conf.get_default()
                    default_conf.auth_token = token
                    # Try to persist token to config file as a fallback
                    try:
                        cfg_path = default_conf.config_path
                        if cfg_path:
                            try:
                                os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
                            except Exception:
                                pass
                            try:
                                content = ""
                                try:
                                    with open(cfg_path, "r", encoding="utf-8") as f:
                                        content = f.read()
                                except Exception:
                                    content = ""
                                if "authtoken" in content.lower():
                                    # Replace existing authtoken line
                                    lines = content.splitlines()
                                    for i, line in enumerate(lines):
                                        if "authtoken" in line.lower():
                                            lines[i] = f"authtoken: {token}"
                                    content = "\n".join(lines)
                                else:
                                    # Minimal config write
                                    content = f"authtoken: {token}\n"
                                with open(cfg_path, "w", encoding="utf-8") as f:
                                    f.write(content)
                            except Exception:
                                pass
                    except Exception:
                        pass
                except Exception:
                    pass
                try:
                    os.environ["NGROK_AUTHTOKEN"] = token
                except Exception:
                    pass
                
                # 1. Check local bin
                current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # voca_app/frontend/.. -> voca_app
                # Actually __file__ is voca_app/frontend/main_ui.py
                # os.path.dirname(__file__) -> frontend
                # os.path.dirname(...) -> voca_app
                # os.path.dirname(...) -> .cursor/voice (root)
                
                # Correct logic to find project root from frontend/main_ui.py
                # root is c:\Users\user\.cursor\voice
                # main_ui is c:\Users\user\.cursor\voice\voca_app\frontend\main_ui.py
                
                root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                bin_dir = os.path.join(root_dir, "bin")
                ngrok_exe = os.path.join(bin_dir, "ngrok.exe")
                
                ngrok_path = None
                if os.path.exists(ngrok_exe):
                    ngrok_path = ngrok_exe
                else:
                    # Fallback to pyngrok's path
                    try:
                        from pyngrok import conf
                        ngrok_path = conf.get_default().ngrok_path
                    except:
                        pass
                
                if not ngrok_path or not os.path.exists(ngrok_path):
                    # As a last resort, assume it's in PATH or try to use the one we expect pyngrok to have installed
                    ngrok_path = "ngrok"
                
                print(f"Configuring ngrok with path: {ngrok_path}")
                
                # Prepare command
                cmd = [ngrok_path, "config", "add-authtoken", token]
                
                # Hide console window
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                
                try:
                    subprocess.run(cmd, check=True, startupinfo=startupinfo)
                except Exception:
                    # If CLI not present, rely on pyngrok runtime and config file we wrote
                    pass
                
                messagebox.showinfo("Success", "Token saved successfully!\n\nStarting secure Internet link...", parent=dialog)
                dialog.destroy()
                
                # Start ngrok tunnel immediately and update UI
                try:
                    self.remote_access_var.set(True)
                except Exception:
                    pass
                try:
                    self.refresh_ngrok_tunnel()
                except Exception:
                    # Fallback to manager start
                    try:
                        self.web_server_manager.start(True)
                    except Exception:
                        pass
                
            except Exception as e:
                print(f"Token Save Error: {e}")
                error_label.config(text=f"Error: {str(e)[:50]}...")
                messagebox.showerror("Configuration Error", f"Could not save token.\n\nDetails: {e}\n\nTry running manually: ngrok config add-authtoken <token>", parent=dialog)

        Button(dialog, text="3. Save Token & Connect", command=save_token, 
               bg="#0078D4", fg="white", font=("Arial", 11, "bold"), padx=20, pady=5, cursor="hand2").pack(pady=10)

    def web_server_log(self, message):
        """Callback for web server logs"""
        # Run on main thread to be safe
        self.root.after(0, lambda: self.append_log(message))
    
    def show_qr_code(self, url=None):
        """Display QR Code with IP selection support"""
        # If no URL provided, try best-available current link
        if not url:
            if hasattr(self, 'web_server') and self.web_server:
                prefer_public = False
                try:
                    if hasattr(self, 'remote_access_var'):
                        prefer_public = bool(self.remote_access_var.get())
                except Exception:
                    prefer_public = False
                
                if prefer_public:
                    if self.web_server.public_url and "http" in str(self.web_server.public_url):
                        url = self.web_server.public_url
                    else:
                        try:
                            self.web_server.set_callback(self.on_web_message, self.web_server_log)
                            started = self.web_server.start(use_ngrok=True)
                            if started and started != "AUTH_REQUIRED":
                                url = self.web_server.public_url or started
                            elif started == "AUTH_REQUIRED":
                                from tkinter import messagebox
                                messagebox.showwarning("Remote Access Required", "Please configure ngrok authtoken to enable Internet access.\nUse the Remote Access setup in the app.", parent=self.root)
                        except Exception:
                            pass
                if not url:
                    url = self.web_server.local_url or (self.web_server.public_url if (self.web_server.public_url and "http" in str(self.web_server.public_url)) else None)
            if not url and hasattr(self, 'web_url') and self.web_url:
                url = self.web_url
        
        # If still no URL, try to auto-start local or public server based on preference
        if not url:
            try:
                if hasattr(self, 'web_server') and self.web_server:
                    self.web_server.set_callback(self.on_web_message, self.web_server_log)
                    prefer_public = False
                    try:
                        if hasattr(self, 'remote_access_var'):
                            prefer_public = bool(self.remote_access_var.get())
                    except Exception:
                        prefer_public = False
                    started = self.web_server.start(use_ngrok=prefer_public)
                    if started:
                        if prefer_public and started != "AUTH_REQUIRED":
                            url = self.web_server.public_url or started
                        else:
                            url = self.web_server.local_url or started
            except Exception:
                pass
        
        # Prefer non-loopback local IP for initial QR
        try:
            if hasattr(self, 'web_server') and self.web_server and isinstance(url, str):
                # Force HTTP for private LAN hosts (avoid HTTPS self-signed issues)
                try:
                    if url.startswith("https://"):
                        hostpart = url.split("://", 1)[1].split("/", 1)[0]
                        host = hostpart.split(":")[0]
                        is_private = (
                            host.startswith("192.168.") or
                            host.startswith("10.") or
                            host.startswith("127.") or
                            (host.startswith("172.") and 16 <= int(host.split(".")[1]) <= 31)
                        )
                        if is_private:
                            port = getattr(self.web_server, 'port', 5050)
                            url = f"http://{host}:{port}"
                except Exception:
                    pass
                if url.startswith("http://127."):
                    if hasattr(self.web_server, 'available_ips'):
                        for ip in self.web_server.available_ips:
                            if not ip.startswith("127."):
                                url = f"http://{ip}:{self.web_server.port}"
                                break
        except Exception:
            pass
            
        if not url:
            from tkinter import messagebox
            messagebox.showerror("Error", "No URL available to generate QR Code.")
            return

        print(f"DEBUG: Showing QR Code for URL: {url}")

        try:
            import qrcode
            from PIL import ImageTk, Image
        except ImportError:
            try:
                # Install qrcode library if missing
                import subprocess
                print("Installing qrcode[pil]...")
                subprocess.check_call([sys.executable, "-m", "pip", "install", "qrcode[pil]"])
                import qrcode
                from PIL import ImageTk, Image
            except Exception as e:
                print(f"Error installing QR lib: {e}")
                from tkinter import messagebox
                messagebox.showerror("Error", f"Could not install QR Code library: {e}")
                return

        try:
            qr_window = Toplevel(self.root)
            qr_window.title("Scan to Connect")
            qr_window.geometry("450x750") # Taller and wider for options
            qr_window.configure(bg='#1e1e1e')
            
            # Make sure window is on top
            qr_window.transient(self.root)
            qr_window.grab_set()
            qr_window.focus_force()
            
            Label(qr_window, text="Scan with your Phone Camera", 
                  font=("Arial", 14, "bold"), fg="white", bg="#1e1e1e").pack(pady=(20, 10))
            
            # QR Image Label (placeholder)
            qr_label = Label(qr_window, bg='#1e1e1e')
            qr_label.pack(pady=10)
            
            # URL Label
            url_label = Label(qr_window, text=url, wraplength=350,
                  font=("Arial", 10), fg="#ccc", bg="#1e1e1e")
            url_label.pack(pady=5)
            
            # Function to update QR
            def update_qr(new_url):
                qr = qrcode.QRCode(version=1, box_size=10, border=4)
                qr.add_data(new_url)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                img_tk = ImageTk.PhotoImage(img)
                qr_label.configure(image=img_tk)
                qr_label.image = img_tk
                url_label.configure(text=new_url)
                
                # Update main app state if it's a local IP
                if "ngrok" not in new_url and hasattr(self, 'web_server'):
                    self.web_server.local_url = new_url
                    if hasattr(self, 'local_link_label'):
                        self.local_link_label.config(text=f"Home Wi-Fi: {new_url} (Click to change IP)")

            # Initial draw
            update_qr(url)
            
            # IP Selection (if multiple)
            ips = []
            if hasattr(self, 'web_server') and self.web_server:
                if hasattr(self.web_server, 'available_ips'):
                    for ip in self.web_server.available_ips:
                        if ip.startswith("127."): continue
                        ips.append(f"Local (Wi-Fi): http://{ip}:{self.web_server.port}")
                try:
                    if getattr(self.web_server, 'https_port', None):
                        if hasattr(self.web_server, 'available_ips'):
                            for ip in self.web_server.available_ips:
                                if ip.startswith("127."): continue
                                ips.append(f"Local (HTTPS): https://{ip}:{self.web_server.https_port}")
                except Exception:
                    pass
                
                if self.web_server.public_url and "http" in self.web_server.public_url:
                    ips.append(f"Public (Internet): {self.web_server.public_url}")
            
            if len(ips) > 0:
                Label(qr_window, text="Select Connection Address:", fg="#888", bg="#1e1e1e", font=("Arial", 10, "bold")).pack(pady=(15, 5))
                Label(qr_window, text="(Try each one if the first fails)", fg="#666", bg="#1e1e1e", font=("Arial", 8)).pack(pady=(0, 5))
                
                # Scrollable frame for IPs if many
                ip_frame = Frame(qr_window, bg='#1e1e1e')
                ip_frame.pack(fill='both', expand=True, padx=20)
                
                # Use Radiobuttons for clearer selection
                self.ip_var = StringVar(value=ips[0]) # Default to first
                
                # Find current to select it
                for ip_str in ips:
                     if url in ip_str:
                         self.ip_var.set(ip_str)
                         break
                
                try:
                    for ip_str in ips:
                        if ip_str.startswith("Local (Wi-Fi):"):
                            self.ip_var.set(ip_str)
                            sel_url = ip_str.split(": ", 1)[1]
                            update_qr(sel_url)
                            break
                except Exception:
                    pass

                def on_radio_change():
                    sel = self.ip_var.get()
                    if ": " in sel:
                        new_url = sel.split(": ", 1)[1]
                        update_qr(new_url)

                for ip_str in ips:
                    rb = Radiobutton(ip_frame, text=ip_str, variable=self.ip_var, value=ip_str,
                                    command=on_radio_change, bg='#1e1e1e', fg='#ccc', 
                                    selectcolor='#333', activebackground='#1e1e1e', activeforeground='white',
                                    font=("Consolas", 9), anchor='w', justify='left')
                    rb.pack(fill='x', pady=2)
                
                def test_links():
                    try:
                        import threading, ssl, urllib.request
                        candidates = []
                        for ip_str in ips:
                            if ": " in ip_str:
                                candidates.append(ip_str.split(": ", 1)[1])
                        if isinstance(url, str):
                            candidates.insert(0, url)
                        # Prefer HTTPS when available for mic/camera, but test HTTP too
                        try:
                            extras = []
                            for cand in list(candidates):
                                if cand.startswith("http://"):
                                    hostpart = cand.split("://", 1)[1].split("/", 1)[0]
                                    host = hostpart.split(":")[0]
                                    is_private = (
                                        host.startswith("192.168.") or
                                        host.startswith("10.") or
                                        host.startswith("127.") or
                                        (host.startswith("172.") and 16 <= int(host.split(".")[1]) <= 31)
                                    )
                                    if is_private and getattr(self.web_server, 'https_port', None):
                                        extras.append(f"https://{host}:{self.web_server.https_port}")
                            candidates = extras + candidates
                        except Exception:
                            pass
                        def run_tests():
                            for cand in candidates:
                                u = cand.rstrip('/') + '/ping'
                                try:
                                    if u.startswith("https://"):
                                        ctx = ssl._create_unverified_context()
                                        urllib.request.urlopen(u, timeout=3, context=ctx)
                                    else:
                                        urllib.request.urlopen(u, timeout=3)
                                    def apply():
                                        for s in ips:
                                            if cand in s:
                                                self.ip_var.set(s)
                                                break
                                        update_qr(cand)
                                    self.root.after(0, apply)
                                    return
                                except Exception:
                                    continue
                            def nohit():
                                try:
                                    from tkinter import messagebox
                                    messagebox.showwarning("Connection Test", "No reachable address was found.\nStarting Internet link automatically...", parent=qr_window)
                                except Exception:
                                    pass
                                try:
                                    self.remote_access_var.set(True)
                                    self.refresh_ngrok_tunnel()
                                    if hasattr(self, 'web_server') and self.web_server and self.web_server.public_url and "http" in self.web_server.public_url:
                                        update_qr(self.web_server.public_url)
                                except Exception:
                                    pass
                            self.root.after(0, nohit)
                        threading.Thread(target=run_tests, daemon=True).start()
                    except Exception:
                        pass
                
                Button(qr_window, text="Test Links", command=test_links,
                       bg='#444', fg='white', font=("Arial", 10, "bold")).pack(pady=8)
                
                try:
                    self.root.after(200, test_links)
                except Exception:
                    pass
                
                def _current_url():
                    try:
                        sel = self.ip_var.get()
                        if ": " in sel:
                            return sel.split(": ", 1)[1]
                    except Exception:
                        pass
                    try:
                        return url_label.cget("text")
                    except Exception:
                        return url
                
                def open_on_pc():
                    try:
                        import webbrowser
                        u = _current_url()
                        if isinstance(u, str):
                            webbrowser.open(u)
                    except Exception:
                        pass
                
                def self_test():
                    try:
                        import ssl, urllib.request
                        u = _current_url()
                        if not isinstance(u, str) or not u:
                            return
                        try:
                            if u.startswith("https://"):
                                hostpart = u.split("://", 1)[1].split("/", 1)[0]
                                host = hostpart.split(":")[0]
                                is_private = (
                                    host.startswith("192.168.") or
                                    host.startswith("10.") or
                                    host.startswith("127.") or
                                    (host.startswith("172.") and 16 <= int(host.split(".")[1]) <= 31)
                                )
                                if is_private:
                                    port = getattr(self.web_server, 'port', 5050)
                                    u = f"http://{host}:{port}"
                            p = u.rstrip('/') + '/ping'
                            try:
                                if p.startswith("https://"):
                                    ctx = ssl._create_unverified_context()
                                    urllib.request.urlopen(p, timeout=3, context=ctx)
                                else:
                                    urllib.request.urlopen(p, timeout=3)
                                from tkinter import messagebox
                                messagebox.showinfo("Self-Test", "Link reachable from this PC.\nOpening in browser.", parent=qr_window)
                                open_on_pc()
                            except Exception as e:
                                from tkinter import messagebox
                                messagebox.showwarning("Self-Test", f"Link not reachable from this PC.\n{e}", parent=qr_window)
                        except Exception:
                            pass
                    except Exception:
                        pass
                
                Button(qr_window, text="Open On This PC", command=open_on_pc,
                       bg='#0078D4', fg='white', font=("Arial", 10, "bold")).pack(pady=6)
                Button(qr_window, text="Self-Test (PC)", command=self_test,
                       bg='#555', fg='white', font=("Arial", 10, "bold")).pack(pady=6)
                
            # Firewall Help
            def run_firewall_fix():
                http_port = 8080
                https_port = None
                if hasattr(self, 'web_server') and self.web_server:
                    http_port = getattr(self.web_server, 'port', 8080)
                    https_port = getattr(self.web_server, 'https_port', None)
                
                cmd_http = f'netsh advfirewall firewall add rule name="VocaAI HTTP {http_port}" dir=in action=allow protocol=TCP localport={http_port} profile=any'
                cmd_https = None
                if https_port:
                    cmd_https = f'netsh advfirewall firewall add rule name="VocaAI HTTPS {https_port}" dir=in action=allow protocol=TCP localport={https_port} profile=any'
                
                # Copy to clipboard first
                self.root.clipboard_clear()
                combined = cmd_http + (('\n' + cmd_https) if cmd_https else '')
                self.root.clipboard_append(combined)
                
                # Try to run automatically (might fail without admin, but worth a shot)
                try:
                    import subprocess
                    # First try direct netsh (non-admin); if fails, elevate
                    if cmd_https:
                        direct_cmd = cmd_http + " & " + cmd_https
                    else:
                        direct_cmd = cmd_http
                    direct_res = subprocess.run(["powershell", "-NoProfile", "-Command", direct_cmd], capture_output=True, text=True, shell=False)
                    if direct_res.returncode == 0:
                        from tkinter import messagebox
                        messagebox.showinfo("Firewall Fix", "Firewall rules added successfully.", parent=qr_window)
                        return
                    # Use PowerShell to run as admin
                    if cmd_https:
                        ps_inner = f"{cmd_http}; {cmd_https}"
                    else:
                        ps_inner = cmd_http
                    ps_cmd = f"Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -Command \"{ps_inner}\"'"
                    subprocess.Popen(["powershell", "-Command", ps_cmd], shell=True)
                    
                    from tkinter import messagebox
                    messagebox.showinfo("Firewall Fix", "Attempting to allow inbound on HTTP/HTTPS ports.\n\nIf a UAC prompt appears, click YES.\n\nIf it fails, open PowerShell as Admin and paste the command (already copied).", parent=qr_window)
                except Exception as e:
                     from tkinter import messagebox
                     messagebox.showerror("Error", f"Could not run automatically: {e}\n\nPlease paste the command manually into Admin PowerShell.", parent=qr_window)

            fw_frame = Frame(qr_window, bg='#2a2a2a', padx=10, pady=10)
            fw_frame.pack(fill='x', padx=20, pady=20)
            
            Label(fw_frame, text="STILL NOT CONNECTING?", fg="#ff5252", bg='#2a2a2a', font=("Arial", 11, "bold")).pack(anchor='w')
            Label(fw_frame, text="Windows Firewall is likely blocking the connection.", 
                  fg="#ccc", bg='#2a2a2a', justify='left', wraplength=320).pack(anchor='w', pady=5)
                  
            Button(fw_frame, text="🛠️ Fix Firewall (Run as Admin)", command=run_firewall_fix,
                   bg='#d32f2f', fg='white', font=("Arial", 10, "bold"), padx=10, pady=5).pack(pady=5, fill='x')
            
            Label(fw_frame, text="(Command also copied to clipboard)", fg="#888", bg='#2a2a2a', font=("Arial", 8)).pack()
            
            def force_public():
                try:
                    self.remote_access_var.set(True)
                    self.refresh_ngrok_tunnel()
                    if hasattr(self, 'web_server') and self.web_server and self.web_server.public_url and "http" in self.web_server.public_url:
                        update_qr(self.web_server.public_url)
                except Exception:
                    pass
            
            Button(qr_window, text="Use Internet Link Instead", command=force_public,
                   bg='#00A3FF', fg='white', font=("Arial", 10, "bold")).pack(pady=6, fill='x')

            Button(qr_window, text="Close", command=qr_window.destroy,
                   bg='#333', fg='white', font=("Arial", 10)).pack(pady=10)
                   
            print("DEBUG: QR Window displayed successfully")
            
        except Exception as e:
            print(f"Error showing QR window: {e}")
            import traceback
            traceback.print_exc()
            from tkinter import messagebox
            messagebox.showerror("Error", f"Failed to display QR Code: {e}")

    def _switch_ip(self, new_url):
        """Helper to switch the displayed IP and update QR code"""
        self.web_server.local_url = new_url
        self.local_link_label.config(text=f"Home Wi-Fi: {new_url} (Click to change IP)")
        
        # Update main web_url if we are in local mode
        if not self.web_server.public_url:
            self.web_url = new_url
            display_url = self.web_url
            if len(display_url) > 30:
                display_url = display_url[:15] + "..." + display_url[-10:]
            if hasattr(self, 'mobile_link_label'):
                self.mobile_link_label.config(text=f"Mobile: {display_url}")
                # Re-bind click
                try:
                    import webbrowser
                    self.mobile_link_label.bind("<Button-1>", lambda e: webbrowser.open(self.web_url))
                except Exception:
                    pass
        
        # Update QR button if it points to local
        if hasattr(self, 'btn_qr'):
             self.btn_qr.config(command=lambda: self.show_qr_code(new_url))
             
        # Auto-show QR for the new IP to save a click
        self.show_qr_code(new_url)

    def host_network(self):
        """Start hosting a session using the isolated web server manager."""
        try:
            self.mobile_link_label.config(text="Status: Starting Server...", fg='#888')
            self.root.update()
            try:
                # Ensure a clean manager state before starting
                self.web_server_manager.stop()
            except Exception:
                pass
            try:
                # Disable controls while starting
                self.btn_host.config(state='disabled', bg='#222')
                self.btn_connect.config(state='disabled', bg='#222')
                if hasattr(self, 'btn_remote_join'):
                    self.btn_remote_join.config(state='disabled', bg='#222')
                self.ip_entry.config(state='disabled')
            except Exception:
                pass
            
            use_ngrok = self.remote_access_var.get()
            # Pass preferred hostname to the manager
            try:
                if hasattr(self, 'web_server_manager'):
                    desired = self.hostname_entry.get().strip() if hasattr(self, 'hostname_entry') else ""
                    self.web_server_manager.preferred_hostname = desired if desired else None
            except Exception:
                pass
            self.web_server_manager.start(use_ngrok)
            
            # Fast watchdog: if no status within 2s, force-start locally/public
            def _force_start():
                try:
                    has_url = bool(self.web_url)
                    if not has_url:
                        srv = VocaWebServer()
                        srv.set_callback(self.on_web_message, self.web_server_log)
                        url = srv.start(use_ngrok=use_ngrok)
                        if url:
                            self.web_server = srv
                            self.on_web_server_status("RUNNING", {"url": url, "local_url": srv.local_url, "public_url": srv.public_url})
                            try:
                                self.show_qr_code(url)
                            except Exception:
                                pass
                        else:
                            from tkinter import messagebox
                            messagebox.showwarning("Host Startup", "Could not create a shareable link yet. Try 'Use Cloudflare Link' or 'Public IP (Guide)'.")
                except Exception:
                    pass
            try:
                import threading
                threading.Timer(2.0, _force_start).start()
            except Exception:
                _force_start()

        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("Host Error", f"Failed to start host session: {e}")
            self.reset_network()
        
    def connect_network(self):
        """Connect to a host"""
        ip = self.ip_entry.get().strip()
        
        if not ip:
            from tkinter import messagebox
            messagebox.showwarning("Enter IP Address", "Please enter the Partner's IP Address first.\n\nAsk the Host for their 'Home Wi-Fi' IP (e.g., 192.168.1.5).")
            return
            
        if ip:
            self.network.connect_to_session(ip)
            self.btn_host.config(state='disabled', bg='#222')
            self.btn_connect.config(state='disabled', bg='#222')
            if hasattr(self, 'btn_remote_join'):
                self.btn_remote_join.config(state='disabled', bg='#222')
            self.ip_entry.config(state='disabled')
            
    def join_remote_session(self):
        """Ask user for a remote URL and open it in browser"""
        from tkinter import simpledialog, messagebox
        import webbrowser
        
        url = simpledialog.askstring("Join Remote Session", "Enter the Internet Link shared by the host:\n(e.g., https://xxxx-xx.ngrok-free.app)", parent=self.root)
        
        if url:
            if not url.startswith("http"):
                url = "https://" + url
                
            try:
                webbrowser.open(url)
                messagebox.showinfo("Browser Opened", "Opening the session in your default browser.\n\nYou can communicate via the web interface.", parent=self.root)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to open link: {e}", parent=self.root)
    
    def refresh_ngrok_tunnel(self):
        try:
            self.remote_link_label.config(text="Internet: Refreshing...", fg='#00A3FF')
            self.root.update()
            if hasattr(self, 'web_server') and self.web_server:
                try:
                    self.web_server.stop()
                except:
                    pass
                self.web_server.set_callback(self.on_web_message, self.web_server_log)
                url = self.web_server.start(use_ngrok=True)
                if url and url != "AUTH_REQUIRED" and "http" in url:
                    display_url = url
                    if len(display_url) > 30:
                        display_url = display_url[:15] + "..." + display_url[-10:]
                    self.remote_link_label.config(text=f"Internet: {display_url}", fg='#00A3FF')
                    self.btn_copy_link.config(state='normal', bg='#444', command=self.copy_remote_link)
                    self.btn_whatsapp.config(state='normal', bg='#25D366', command=self.share_whatsapp)
                    if hasattr(self, 'btn_qr'):
                        self.btn_qr.config(state='normal', command=lambda u=url: self.show_qr_code(u))
                    try:
                        import webbrowser
                        self.remote_link_label.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
                    except Exception:
                        pass
                    if hasattr(self, 'btn_open_remote'):
                        self.btn_open_remote.config(state='normal', bg='#444')
                elif url == "AUTH_REQUIRED":
                    self.remote_link_label.config(text="Status: MISSING AUTH TOKEN", fg='red')
                    if not self.ngrok_prompt_shown:
                        self.ngrok_prompt_shown = True
                        self.show_ngrok_setup_dialog()
                else:
                    self.remote_link_label.config(text="Internet: Disabled", fg='#00A3FF')
        except Exception as e:
            pass
    
    def show_network_help(self):
        """Show help dialog for networking"""
        from tkinter import Toplevel, Label, Button, Text, Scrollbar
        
        help_win = Toplevel(self.root)
        help_win.title("VocaAI Network Help")
        help_win.geometry("500x400")
        help_win.configure(bg='#1e1e1e')
        help_win.transient(self.root)
        
        Label(help_win, text="How to Connect", font=("Arial", 14, "bold"), fg="white", bg="#1e1e1e").pack(pady=10)
        
        content = Text(help_win, bg='#222', fg='#ddd', font=("Arial", 10), relief='flat', padx=10, pady=10)
        content.pack(fill='both', expand=True, padx=10, pady=5)
        
        msg = """1. LOCAL WI-FI (Same House):
   - HOST: Click 'HOST'. Share the 'Home Wi-Fi' link/IP.
   - JOIN: Enter the Host's IP (e.g. 192.168.x.x) in 'Partner IP' box.
   - Click 'JOIN (Enter IP)'.

2. REMOTE INTERNET (Different Places):
   - Check 'Enable Remote Access'.
   - Click 'HOST'.
   - If asked, follow the steps to get a free Ngrok Token (one-time setup).
   - Share the 'Internet' link (https://...).
   - The other person can click the link directly or use 'JOIN (WEB)'.

TROUBLESHOOTING:
- "MISSING AUTH TOKEN": You need a free account at ngrok.com. Click HOST again to see the setup guide.
- "Web Server Failed": Check if another app is using port 8080.
- "Connecting...": Ensure both devices are online.
"""
        content.insert('1.0', msg)
        content.config(state='disabled')
        
        Button(help_win, text="Close", command=help_win.destroy, bg='#444', fg='white').pack(pady=10)

    def reset_network(self):
        """Reset network state and allow new connections"""
        if hasattr(self, 'network'):
            self.network.disconnect()
            
        if hasattr(self, 'web_server'):
            try:
                self.web_server.stop()
            except:
                pass
            # Re-create server instance to ensure clean state
            self.web_server = VocaWebServer() # Use default port 5050
            self.web_server.set_callback(self.on_web_message)
            self.web_url = None
            
        self.btn_host.config(state='normal', bg='#4CAF50')
        self.btn_connect.config(state='normal', bg='#0078D4')
        if hasattr(self, 'btn_remote_join'):
            self.btn_remote_join.config(state='normal', bg='#00BCD4')
        self.ip_entry.config(state='normal')
        self.chk_remote.config(state='normal')
        # Reset to True for HTTPS default
        self.remote_access_var.set(True)
        self.mobile_link_label.config(text="")
        
        # Reset new labels and buttons
        if hasattr(self, 'local_link_label'):
            self.local_link_label.config(text="")
        if hasattr(self, 'remote_link_label'):
            self.remote_link_label.config(text="")
        if hasattr(self, 'btn_copy_link'):
            self.btn_copy_link.config(state='disabled', bg='#333', text="📋 Copy")
        if hasattr(self, 'btn_whatsapp'):
            self.btn_whatsapp.config(state='disabled')
        if hasattr(self, 'btn_qr'):
            self.btn_qr.config(state='normal', command=lambda: self.show_qr_code(None))
        if hasattr(self, 'btn_open_remote'):
            self.btn_open_remote.config(state='disabled', bg='#333')
        if hasattr(self, 'btn_refresh_ngrok'):
            self.btn_refresh_ngrok.config(state='disabled')
            
        # Reset labels
        if hasattr(self, 'net_status_var'):
            self.net_status_var.set("OFFLINE")
            self.net_status_label.config(fg='#888')

    def on_web_message(self, payload):
        """Handle incoming messages from mobile web client"""
        print(f"UI: Received Web Message: {payload}")
        # Treat same as network message for now
        self.on_network_message(payload)
        
    def show_share_dialog(self):
        from tkinter import Toplevel, Label, Button, Entry, messagebox
        import webbrowser
        import urllib.parse
        url = None
        try:
            if hasattr(self, 'web_server') and self.web_server:
                if self.web_server.public_url and "http" in str(self.web_server.public_url):
                    url = self.web_server.public_url
                elif self.web_server.local_url:
                    url = self.web_server.local_url
        except Exception:
            url = None
        if not url and hasattr(self, 'web_url') and self.web_url:
            url = self.web_url
        if not url:
            try:
                self.refresh_ngrok_tunnel()
                if hasattr(self, 'web_server') and self.web_server and self.web_server.public_url and "http" in self.web_server.public_url:
                    url = self.web_server.public_url
                elif hasattr(self, 'web_server') and self.web_server and self.web_server.local_url:
                    url = self.web_server.local_url
            except Exception:
                pass
        if not url:
            messagebox.showwarning("No Link", "No link available yet. Click HOST, then Check Remote Connectivity.", parent=self.root)
            return
        dlg = Toplevel(self.root)
        dlg.title("Share Link")
        dlg.geometry("420x160")
        dlg.configure(bg='#1e1e1e')
        dlg.transient(self.root)
        Label(dlg, text="Share this link:", fg='white', bg='#1e1e1e', font=('Arial', 11, 'bold')).pack(pady=(12, 6))
        entry = Entry(dlg, width=56, font=('Consolas', 10))
        entry.pack(padx=10)
        entry.insert(0, url)
        def _copy():
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(url)
            except Exception:
                pass
        def _open():
            try:
                webbrowser.open(url)
            except Exception:
                pass
        def _qr():
            try:
                self.show_qr_code(url)
            except Exception:
                pass
        btn_frame = Frame(dlg, bg='#1e1e1e')
        btn_frame.pack(pady=10)
        Button(btn_frame, text="Copy", command=_copy, bg='#444', fg='white', padx=10, pady=4).pack(side='left', padx=4)
        Button(btn_frame, text="Open", command=_open, bg='#444', fg='white', padx=10, pady=4).pack(side='left', padx=4)
        Button(btn_frame, text="QR", command=_qr, bg='#444', fg='white', padx=10, pady=4).pack(side='left', padx=4)
        Button(dlg, text="Close", command=dlg.destroy, bg='#333', fg='white').pack(pady=(0,10))
        
    def copy_remote_link(self):
        """Copy the link to clipboard (Remote or Local)"""
        url = None
        if self.web_server.public_url and "http" in self.web_server.public_url:
            url = self.web_server.public_url
        elif self.web_server.local_url:
            url = self.web_server.local_url
            
        if url:
            self.root.clipboard_clear()
            self.root.clipboard_append(url)
            self.btn_copy_link.config(text="✅ Copied!")
            self.root.after(2000, lambda: self.btn_copy_link.config(text="📋 Copy"))
            
    def share_whatsapp(self):
        """Share the link via WhatsApp Web"""
        url = None
        if self.web_server.public_url and "http" in self.web_server.public_url:
            url = self.web_server.public_url
        elif self.web_server.local_url:
            url = self.web_server.local_url
            
        if url:
            text = f"Connect to my VocaAI session here: {url}"
            wa_url = f"https://web.whatsapp.com/send?text={urllib.parse.quote(text)}"
            webbrowser.open(wa_url)

    def on_network_message(self, payload):
        """Handle incoming network messages"""
        print(f"UI: Received Network Message: {payload}")
        try:
            msg_type = payload.get("type")
            content = payload.get("content")
            
            if msg_type == "SIGN":
                display_text = f"[REMOTE]: {content}"
                # Use after() to ensure thread safety
                self.root.after(0, lambda: self.history_var.set(display_text))
                self.root.after(0, lambda: self.update_history_log(display_text))
                
            elif msg_type == "VOICE":
                display_text = f"[REMOTE]: {content}"
                print(f"UI: Processing REMOTE VOICE: {display_text}")
                
                # Update the voice text state so update_gui picks it up
                self.voice_text = display_text
                self.last_voice_captured = display_text # Update for HUD
                self.voice_text_timer = time.time() + 10 # Show for 10 seconds (same as local)
                self.voice_status_override = False
                
                # Update history log as well for visibility
                self.root.after(0, lambda: self.update_history_log(display_text))
                
                # Immediate update for responsiveness (similar to on_voice_detected)
                def update_remote_voice_ui():
                    v_prefix = self.translations[self.current_lang]['voice']
                    self.voice_var.set(f"{v_prefix}: {display_text}")
                    self.voice_label.config(
                        fg='#00FFD1', 
                        bg='#1a1a1a',
                        font=('Arial', 12, 'bold')
                    )
                    self.voice_label.lift()
                    
                self.root.after(0, update_remote_voice_ui)
                
        except Exception as e:
            print(f"Message Handler Error: {e}")

    def update_gui(self):
        """Update GUI periodically using root.after() for thread safety"""
        if not self.running:
            return
            
        try:
            current_time = time.time()
            
            # Update Network Status
            if hasattr(self, 'network'):
                self.net_status_var.set(self.network.status)
                if self.network.connected:
                    self.net_status_label.config(fg='#4CAF50') # Green
                elif "WAITING" in self.network.status or "CONNECTING" in self.network.status:
                     self.net_status_label.config(fg='#FFC107') # Amber
                else:
                    self.net_status_label.config(fg='#888') # Grey
                    
                # Auto-reset buttons if network stopped (e.g. error or disconnect)
                if not self.network.running and not self.network.connected:
                     if self.btn_host['state'] == 'disabled':
                         self.btn_host.config(state='normal', bg='#4CAF50')
                         self.btn_connect.config(state='normal', bg='#0078D4')
                         if hasattr(self, 'btn_remote_join'):
                             self.btn_remote_join.config(state='normal', bg='#00BCD4')
                         self.ip_entry.config(state='normal')
            
            # Update Sidebar Analytics
            sentence = self.sentence_buffer.get_sentence()
            self.transcript_var.set(sentence if sentence else self.translations[self.current_lang]['waiting'])
            
            # Update Natural Translation
            if self.sentence_buffer.history:
                last_sent = self.sentence_buffer.history[-1]
                if self.history_var.get() != last_sent:
                    self.history_var.set(last_sent)
                    self.update_history_log(last_sent)
                    # Save to Database
                    self.db.add_entry("SIGN", last_sent, self.current_lang)
                    # Send to Network
                    if hasattr(self, 'network'):
                        self.network.send_message("SIGN", last_sent)
                    # Send to Web
                    if hasattr(self, 'web_server') and self.web_server.running:
                        self.web_server.broadcast_update("TRANSCRIPT", last_sent)
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
            
            # Update Mic Status
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
                frame = None
                local_frame = None
                remote_frame = None
                is_remote = False
                
                # 1. Always get local camera if available (for PIP or fallback)
                if self.cap.isOpened():
                    ret, raw_local = self.cap.read()
                    if ret:
                        local_frame = cv2.flip(raw_local, 1) # Flip local mirror

                # 2. Check for remote frame from WebServer with Timeout Check (only use running server)
                if hasattr(self, 'web_server') and self.web_server and getattr(self.web_server, 'running', False) and self.web_server.remote_sign_active:
                    last_time = getattr(self.web_server, 'last_frame_time', 0)
                    if time.time() - last_time < 2.0:
                        with self.web_server.frame_lock:
                            if self.web_server.latest_frame is not None:
                                remote_frame = self.web_server.latest_frame.copy()
                                is_remote = True
                    else:
                        is_remote = False
                        self.web_server.remote_sign_active = False
                            
                # 3. Determine Main Frame for Processing
                if is_remote and remote_frame is not None:
                    frame = remote_frame
                elif local_frame is not None:
                    frame = local_frame
                
                if frame is not None:
                    # Process frame (MediaPipe is CPU intensive)
                    try:
                        processed_frame = self.process_frame(frame)
                        
                        # OPTIMIZATION: Pre-resize for GUI display to save main thread time
                        h, w = processed_frame.shape[:2]
                        display_h = 720
                        display_w = int(w * (display_h / h))
                        gui_frame = cv2.resize(processed_frame, (display_w, display_h))
                        
                        # DUAL VIEW: Overlay Local Camera (PIP) if Remote is Active
                        if is_remote and local_frame is not None:
                            try:
                                # Resize local frame to PIP size (e.g. 25% width)
                                pip_h, pip_w = local_frame.shape[:2]
                                scale_pip = 0.25
                                new_pip_w = int(display_w * scale_pip)
                                new_pip_h = int(pip_h * (new_pip_w / pip_w))
                                
                                pip_frame = cv2.resize(local_frame, (new_pip_w, new_pip_h))
                                
                                # Position: Bottom Right with margin
                                margin = 20
                                y_offset = display_h - new_pip_h - margin
                                x_offset = display_w - new_pip_w - margin
                                
                                # Ensure bounds
                                if y_offset > 0 and x_offset > 0:
                                    # Draw border
                                    cv2.rectangle(gui_frame, (x_offset-2, y_offset-2), 
                                                (x_offset+new_pip_w+2, y_offset+new_pip_h+2), (0, 255, 0), 2)
                                    gui_frame[y_offset:y_offset+new_pip_h, x_offset:x_offset+new_pip_w] = pip_frame
                                    
                                    # Add label
                                    cv2.putText(gui_frame, "YOU (LAPTOP)", (x_offset, y_offset - 8), 
                                              cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
                            except Exception as e:
                                print(f"PIP Error: {e}")

                        # Add indicator for Remote Camera
                        if is_remote:
                            cv2.putText(gui_frame, "REMOTE CAMERA ACTIVE", (10, 30), 
                                      cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                        
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
                    # No frame available
                    time.sleep(0.1)

            except Exception as e:
                print(f"Video Stream Error: {e}")
                time.sleep(1)
        
            # Small sleep to prevent 100% CPU usage if processing is too fast
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
        if hasattr(self, 'web_server') and self.web_server:
            try:
                print("Stopping Web Server...")
                self.web_server.stop()
            except Exception as e:
                print(f"Error stopping web server: {e}")

        if hasattr(self, 'network') and self.network:
            try:
                print("Stopping Network Client...")
                self.network.disconnect()
            except Exception as e:
                print(f"Error stopping network: {e}")

        if self.cap.isOpened():
            self.cap.release()
        cv2.destroyAllWindows()
        if hasattr(self, 'db'):
            self.db.close()
        self.root.destroy()
        sys.exit(0)

if __name__ == "__main__":
    # If run directly, launch the app for testing
    print("Running VocaAI Translator directly...")
    try:
        root = Tk()
        app = VocaAITranslator(root)
        
        # Ensure window is visible
        root.deiconify()
        
        app.run()
    except KeyboardInterrupt:
        print("Interrupted by user")
    except Exception as e:
        print(f"Fatal Error: {e}")
