
import sys
import os
import time
import threading

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from voca_app.backend.network import NetworkClient
    print("Successfully imported NetworkClient")
except ImportError as e:
    print(f"Failed to import NetworkClient: {e}")
    sys.exit(1)

def test_network():
    print("Testing NetworkClient...")
    
    host = NetworkClient()
    client = NetworkClient()
    
    received_msgs = []
    
    def on_msg(payload):
        print(f"Callback received: {payload}")
        received_msgs.append(payload)
        
    client.set_callback(lambda p: received_msgs.append(("CLIENT_RECV", p)))
    host.set_callback(lambda p: received_msgs.append(("HOST_RECV", p)))
    
    print("Starting host...")
    host.host_session(port=5005)
    time.sleep(1)
    print(f"Host status: {host.status}")
    
    print("Connecting client...")
    client.connect_to_session("127.0.0.1", port=5005)
    time.sleep(1)
    print(f"Client status: {client.status}")
    
    if client.connected:
        print("Connection successful!")
    else:
        print("Connection failed!")
        
    print("Sending message from host to client...")
    host.send_message("SIGN", "Hello Client")
    time.sleep(1)
    
    print("Sending message from client to host...")
    client.send_message("VOICE", "Hello Host")
    time.sleep(1)
    
    print(f"Total messages received: {len(received_msgs)}")
    print(f"Received: {received_msgs}")
    
    host.disconnect()
    client.disconnect()
    
    if len(received_msgs) >= 2:
        print("TEST PASSED")
    else:
        print("TEST FAILED")

if __name__ == "__main__":
    test_network()
