
import sys
import os
import time

# Add the project root to sys.path
sys.path.append(os.path.abspath("."))

from voca_app.backend.web_server import VocaWebServer

print("DEBUG: Starting VocaWebServer test...")
try:
    server = VocaWebServer(port=8080)
    print("DEBUG: Initialized VocaWebServer")
    
    url = server.start(use_ngrok=False)
    print(f"DEBUG: Server started successfully at {url}")
    
    if url:
        print("DEBUG: Success!")
    else:
        print("DEBUG: Failed to get URL (start returned None)")
        
    # Keep it running for a few seconds to verify
    time.sleep(2)
    
    print("DEBUG: Stopping server...")
    server.stop()
    print("DEBUG: Server stopped")
    
except Exception as e:
    print(f"DEBUG: CRITICAL ERROR during server startup: {e}")
    import traceback
    traceback.print_exc()
