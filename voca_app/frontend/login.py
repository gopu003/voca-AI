from tkinter import Tk, Frame, Canvas, Label, Button, Entry
import time

class LoginWindow:
    """Professional Modern Web-style Login Dashboard for VocaAI"""
    def __init__(self, root, on_login_success):
        self.root = root
        self.on_login_success = on_login_success
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
        
        # Ensure window is visible and on top
        self.root.lift()
        self.root.attributes('-topmost', True)
        self.root.after(500, lambda: self.root.attributes('-topmost', False))
        
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
                                   fill='#00221C')
        
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
        
        # Placeholder Logic
        if placeholder:
            entry.insert(0, placeholder)
            entry.config(fg=self.colors['text_dim'])
            
            def on_focus_in(e):
                entry_frame.config(bg=self.colors['accent'])
                if entry.get() == placeholder:
                    entry.delete(0, 'end')
                    entry.config(fg='white')
                    if is_password: entry.config(show="*")
                    
            def on_focus_out(e):
                entry_frame.config(bg='#1A1A1A')
                if not entry.get():
                    entry.insert(0, placeholder)
                    entry.config(fg=self.colors['text_dim'])
                    if is_password: entry.config(show="") # Show placeholder text clearly
            
            entry.bind("<FocusIn>", on_focus_in)
            entry.bind("<FocusOut>", on_focus_out)
            
            # Initial password hide fix
            if is_password: entry.config(show="") 
        else:
             if is_password: entry.config(show="*")
             # Focus effects (Simple)
             entry.bind("<FocusIn>", lambda e: entry_frame.config(bg=self.colors['accent']))
             entry.bind("<FocusOut>", lambda e: entry_frame.config(bg='#1A1A1A'))

        entry.pack(padx=15, pady=12)
        
        return entry

    def interpolate_color(self, c1, c2, t):
        """Simple color interpolation"""
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
            
        if self.on_login_success:
            self.on_login_success(self.root)

if __name__ == "__main__":
    import sys
    import os
    
    # Allow running this file directly for testing
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
    if project_root not in sys.path:
        sys.path.append(project_root)
        
    try:
        from voca_app.frontend.main_ui import VocaAITranslator
    except ImportError:
        # Try adjusting path if running from frontend dir
        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
        from voca_app.frontend.main_ui import VocaAITranslator
    
    def test_login_success(root):
        print("Login successful! Starting Main UI...")
        # Reset root geometry/etc if needed
        root.overrideredirect(False)
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        w = int(screen_width * 0.9)
        h = int(screen_height * 0.9)
        x = (screen_width - w) // 2
        y = (screen_height - h) // 2
        root.geometry(f"{w}x{h}+{x}+{y}")
        
        # Initialize main app attached to root
        app = VocaAITranslator(root)
        
        # Start app components (threads, etc.)
        app.voice_recognizer.start()
        app.root.after(100, app.update_gui)
        
        import threading
        threading.Thread(target=app.process_video_loop, daemon=True).start()

    print("Running Login Window Test Mode...")
    root = Tk()
    login = LoginWindow(root, test_login_success)
    root.mainloop()
