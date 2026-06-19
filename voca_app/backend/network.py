import socket
import threading
import json
import time

class NetworkClient:
    """
    Handles P2P communication for VocaAI.
    Allows two instances to exchange translated text and voice data.
    """
    def __init__(self):
        self.sock = None
        self.running = False
        self.is_host = False
        self.connected = False
        self.remote_addr = None
        self.receive_callback = None
        self.send_queue = []
        self.received_queue = []
        self.status = "OFFLINE"
        self.target_ip = None
        self.target_port = None
        
    def set_callback(self, callback):
        """Set function to call when message received"""
        self.receive_callback = callback
        
    def host_session(self, port=5000):
        """Start a server session"""
        if self.running: return
        
        self.running = True
        self.is_host = True
        self.status = "WAITING FOR CONNECTION..."
        
        threading.Thread(target=self._server_loop, args=(port,), daemon=True).start()
        
    def connect_to_session(self, ip, port=5000):
        """Connect to a host session"""
        if self.running: return
        
        self.running = True
        self.is_host = False
        self.status = f"CONNECTING TO {ip}..."
        self.target_ip = ip
        self.target_port = port
        
        threading.Thread(target=self._client_loop, args=(ip, port), daemon=True).start()
        
    def disconnect(self):
        """Close connection"""
        self.running = False
        self.connected = False
        self.status = "DISCONNECTED"
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
        self.sock = None
        
    def send_message(self, msg_type, content):
        """Send a message (SIGN or VOICE)"""
        if not self.connected or not self.sock:
            return False
            
        try:
            payload = json.dumps({
                "type": msg_type,
                "content": content,
                "timestamp": time.time()
            })
            # Send with newline delimiter for robustness
            msg = (payload + "\n").encode('utf-8')
            self.sock.sendall(msg)
            return True
        except Exception as e:
            print(f"Send Error: {e}")
            self.connected = False
            self.status = "CONNECTION LOST"
            return False
            
    def _get_local_ip(self):
        """Get the actual LAN IP address"""
        try:
            # Connect to a public DNS to determine the outgoing interface
            # No data is actually sent
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except:
            return socket.gethostbyname(socket.gethostname())

    def _server_loop(self, port):
        """Internal server loop"""
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.bind(('0.0.0.0', port))
            server.listen(1)
            
            # Get local IP for display
            local_ip = self._get_local_ip()
            self.status = f"HOSTING ON {local_ip}:{port}"
            print(f"Network: Hosting on {local_ip}:{port}")
            
            while self.running:
                try:
                    server.settimeout(1.0)
                    client, addr = server.accept()
                    self.sock = client
                    self.remote_addr = addr
                    self.connected = True
                    self.status = f"CONNECTED TO {addr[0]}"
                    print(f"Network: Connected to {addr}")
                    
                    self._handle_connection()
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"Server Accept Error: {e}")
                    break
                    
        except Exception as e:
            self.status = f"HOST ERROR: {e}"
            print(f"Host Error: {e}")
            self.running = False # Stop running on bind error
        finally:
            self.running = False
            self.connected = False
            
    def _client_loop(self, ip, port):
        backoff = 2
        while self.running:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(10)
                self.sock.connect((ip, port))
                self.connected = True
                self.status = f"CONNECTED TO {ip}"
                print(f"Network: Connected to {ip}")
                self._handle_connection()
            except Exception as e:
                self.connected = False
                self.status = f"RETRYING IN {backoff}s"
                print(f"Connect Error: {e}")
                time.sleep(backoff)
                backoff = min(backoff * 2, 10)
            finally:
                try:
                    if self.sock:
                        self.sock.close()
                except:
                    pass
                self.sock = None
            if not self.running:
                break
        self.running = False
        self.connected = False
        self.status = "DISCONNECTED"
            
    def _handle_connection(self):
        """Handle sending/receiving loop"""
        buffer = ""
        
        # Use makefile for easier line reading if possible, but keep simple buffer for robustness
        while self.running and self.connected:
            try:
                data = self.sock.recv(4096)
                if not data:
                    break
                    
                msg_str = data.decode('utf-8')
                buffer += msg_str
                
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line: continue
                    
                    try:
                        # Handle case where old clients send without newline (fallback)
                        # This is a bit tricky if they don't use newline, but let's assume new protocol
                        # If JSON fails, try the old split method as fallback
                        payload = json.loads(line)
                        self.received_queue.append(payload)
                        if self.receive_callback:
                            print(f"Network: Received {payload.get('type')}")
                            self.receive_callback(payload)
                    except json.JSONDecodeError:
                        # Fallback for old clients or malformed packets
                        # Try to find valid JSON objects manually if needed
                        # But for now, just print error
                        print(f"JSON Decode Error: {line[:50]}...")
                            
            except ConnectionResetError:
                break
            except Exception as e:
                print(f"Connection Error: {e}")
                break
                
        self.connected = False
        self.status = "DISCONNECTED"
