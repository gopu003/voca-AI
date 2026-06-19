
import sys
import os
import time
import json
import threading
import urllib.request
import urllib.parse
import json

# Add the project root to sys.path so we can import modules
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))

from voca_app.backend.web_server import VocaWebServer

def test_callback(data):
    print(f"TEST CALLBACK RECEIVED: {data}")

def test_log_callback(msg):
    print(f"TEST LOG: {msg}")

def run_test():
    print("Initializing Web Server...")
    server = VocaWebServer(port=8090)
    server.set_callback(test_callback, test_log_callback)
    
    print("Starting Web Server...")
    url = server.start(use_ngrok=False)
    
    if not url:
        print("Failed to start server.")
        return

    print(f"Server started at {url}")
    
    # Wait a bit for server to be ready
    time.sleep(2)
    
    # Send a test message
    test_url = f"{url}/send"
    payload = {"type": "VOICE", "content": "Hello from Test Script"}
    data = json.dumps(payload).encode('utf-8')
    
    req = urllib.request.Request(test_url, data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    
    print(f"Sending POST request to {test_url} with payload: {payload}")
    try:
        with urllib.request.urlopen(req) as response:
            print(f"Response Status Code: {response.getcode()}")
            print(f"Response Text: {response.read().decode('utf-8')}")
            
        print("Message sent successfully.")
            
    except Exception as e:
        print(f"Error sending request: {e}")
        
    # Keep server running for a moment to process request
    time.sleep(2)
    
    print("Stopping server...")
    server.stop()
    print("Test complete.")

if __name__ == "__main__":
    run_test()
