import sys
import os

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Check required packages (cv2, mediapipe, numpy, pyttsx3, PIL) before starting
REQUIRED_PACKAGES = [
    ("cv2", "opencv-python"),
    ("mediapipe", "mediapipe"),
    ("numpy", "numpy"),
    ("pyttsx3", "pyttsx3"),
    ("PIL", "Pillow"),
]
missing = []
for import_name, pip_name in REQUIRED_PACKAGES:
    try:
        __import__(import_name)
    except ImportError:
        missing.append(pip_name)

if missing:
    try:
        import subprocess
        print("Installing missing packages:", ", ".join(missing))
        subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
        # Verify again after install
        still_missing = []
        for import_name, pip_name in REQUIRED_PACKAGES:
            try:
                __import__(import_name)
            except ImportError:
                still_missing.append(pip_name)
        if still_missing:
            msg = (
                "Missing required packages:\n\n" +
                "\n".join(f"  - {p}" for p in still_missing) +
                "\n\nInstall with:\n  pip install " + " ".join(still_missing)
            )
            try:
                from tkinter import Tk, messagebox
                root = Tk()
                root.withdraw()
                messagebox.showerror("Missing Dependencies", msg)
            except Exception:
                print(msg)
            sys.exit(1)
    except Exception as e:
        msg = (
            "Automatic installation failed:\n" +
            str(e) +
            "\n\nPlease run:\n  pip install " + " ".join(missing)
        )
        try:
            from tkinter import Tk, messagebox
            root = Tk()
            root.withdraw()
            messagebox.showerror("Missing Dependencies", msg)
        except Exception:
            print(msg)
        sys.exit(1)

try:
    from tkinter import Tk, Label, messagebox
    from voca_app.frontend.login import LoginWindow
    from voca_app.frontend.main_ui import VocaAITranslator
except ImportError as e:
    # Fallback for missing dependencies
    try:
        import tkinter.messagebox
        root = tkinter.Tk()
        root.withdraw()
        tkinter.messagebox.showerror("Dependency Error", f"Failed to import required modules.\n\nError: {e}\n\nPlease install dependencies: pip install -r requirements.txt")
        sys.exit(1)
    except:
        print(f"Critical Error: {e}")
        sys.exit(1)
except Exception as e:
    # Catch other import-time errors (syntax, etc)
    try:
        import tkinter.messagebox
        root = tkinter.Tk()
        root.withdraw()
        tkinter.messagebox.showerror("Startup Error", f"Failed to start application.\n\nError: {e}")
        sys.exit(1)
    except:
        print(f"Critical Error: {e}")
        sys.exit(1)

def main():
    """Main entry point for VocaAI"""
    try:
        root = Tk()
        
        def on_login_success(app_root):
            try:
                # Reset root configuration that LoginWindow might have changed
                app_root.overrideredirect(False)
                
                # Maximize window or set default size
                screen_width = app_root.winfo_screenwidth()
                screen_height = app_root.winfo_screenheight()
                # Set to 90% of screen size centered
                w = int(screen_width * 0.9)
                h = int(screen_height * 0.9)
                x = (screen_width - w) // 2
                y = (screen_height - h) // 2
                app_root.geometry(f"{w}x{h}+{x}+{y}")
                
                # Initialize main app attached to root
                app = VocaAITranslator(app_root)
                
                # Start app components (threads, etc.)
                # We don't call app.run() because it calls mainloop(), and we are already in a mainloop.
                # Instead we call the start-up methods directly.
                
                app.voice_recognizer.start()
                app.root.after(100, app.update_gui)
                
                import threading
                threading.Thread(target=app.process_video_loop, daemon=True).start()
                
                print("VocaAI Main Interface Loaded")
            except Exception as e:
                print(f"Error starting main app: {e}")
                import traceback
                traceback.print_exc()
                from tkinter import Label
                Label(app_root, text=f"Error starting main app:\n{e}", fg="red", font=("Arial", 14)).pack(pady=20)
            
        # Create Login Window on the root
        login = LoginWindow(root, on_login_success)
        
        # Start the loop
        root.mainloop()
        
    except Exception as e:
        error_msg = f"Fatal Application Error: {e}\n"
        print(error_msg)
        import traceback
        traceback.print_exc()
        
        # Write to log file
        try:
            with open("error_log.txt", "w") as f:
                f.write(error_msg)
                traceback.print_exc(file=f)
        except:
            pass
            
        try:
            # Try to show error in a GUI window if possible
            import tkinter.messagebox
            tkinter.messagebox.showerror("Application Error", f"An error occurred:\n{e}\n\nCheck error_log.txt for details.")
        except:
            pass
        input("Press Enter to close...")

if __name__ == "__main__":
    main()
