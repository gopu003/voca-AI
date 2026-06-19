
import http.server
import socketserver
import threading
import json
import time
import os
import socket
import urllib.parse
from datetime import datetime
import shutil
import sys
import subprocess

try:
    from pyngrok import ngrok, conf
    HAS_NGROK = True
except ImportError:
    HAS_NGROK = False

class VocaWebServer:
    def __init__(self, port=5050):
        self.port = port
        self.server = None
        self.https_port = 5443
        self.https_server = None
        self.https_thread = None
        self.server_thread = None
        self.running = False
        self.clients = [] # List of response streams for SSE
        self.message_callback = None
        self.log_callback = None
        self.latest_transcript = "Waiting..."
        self.latest_voice = "Listening..."
        self.history = []
        self.local_url = None
        self.public_url = None
        self.https_url = None
        self.ngrok_tunnel = None
        self.ngrok_error = None
        self.ngrok_disabled = False
        self.cfd_process = None
        self.cfd_error = None
        self.cfd_url = None
        self.preferred_hostname = None
        self.cert_dir = os.path.join(os.path.abspath(os.getcwd()), "certs")
        self.cert_path = os.path.join(self.cert_dir, "voca_cert.pem")
        self.key_path = os.path.join(self.cert_dir, "voca_key.pem")
        self.upnp_mapped = False
        self.upnp_external_ip = None
        self.upnp_external_port = None
        
        # Remote Camera / Sign Input Support
        self.remote_sign_active = False
        self.latest_frame = None
        self.last_frame_time = 0
        self.frame_lock = threading.Lock()

    def set_callback(self, callback, log_callback=None):
        """Callback for when mobile sends a message (e.g. text/voice)"""
        self.message_callback = callback
        self.log_callback = log_callback

    def log(self, message):
        try:
            with open("server_log.txt", "a", encoding='utf-8') as f:
                f.write(f"{datetime.now()}: {message}\n")
        except Exception:
            pass
        try:
            if self.log_callback:
                self.log_callback(f"WEB: {message}")
        except Exception:
            pass
        try:
            print(f"WEB_SERVER: {message}")
        except Exception:
            pass

    def kill_process_on_port(self, port):
        """Attempts to kill process running on specific port (Windows)"""
        try:
            import subprocess
            # Check if port is in use
            cmd = f"netstat -ano | findstr :{port}"
            # Run command and capture output
            # Use specific startupinfo to hide console window
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)
            output, _ = process.communicate()
            output = output.decode()
            
            if str(port) in output:
                self.log(f"Port {port} appears busy. Attempting to clear...")
                lines = output.strip().splitlines()
                killed_any = False
                for line in lines:
                    parts = line.split()
                    # Example: TCP 0.0.0.0:8080 0.0.0.0:0 LISTENING 1234
                    # We look for the port in the local address part (index 1)
                    if len(parts) >= 5 and f":{port}" in parts[1]:
                        pid = parts[-1]
                        if pid != "0":
                            self.log(f"Killing PID {pid}...")
                            os.system(f"taskkill /F /PID {pid} > nul 2>&1")
                            killed_any = True
                
                if killed_any:
                    time.sleep(1) # Wait for OS to release port
                    return True
        except Exception as e:
            self.log(f"Auto-kill failed: {e}")
        return False

    def has_ngrok_auth(self):
        """Check if ngrok auth token is configured"""
        if not HAS_NGROK: return False
        try:
            # Try to apply local project ngrok config first
            try:
                self._apply_ngrok_config()
            except Exception:
                pass
            # Check config
            if conf.get_default().auth_token: return True
            # Check environment
            if os.environ.get("NGROK_AUTHTOKEN"): return True
            # Check default config file
            config_path = conf.get_default().config_path
            if config_path and os.path.exists(config_path):
                 with open(config_path, 'r') as f:
                     if "authtoken" in f.read(): return True
            # Check project bin/ngrok.yml as fallback
            try:
                proj_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                cfg = os.path.join(proj_root, "bin", "ngrok.yml")
                if os.path.exists(cfg):
                    with open(cfg, 'r') as f:
                        if "authtoken" in f.read(): return True
            except Exception:
                pass
            return False
        except:
            return False

    def get_lan_ip(self):
        """Try multiple methods to get the best LAN IP"""
        # 1. Try connecting to internet (most reliable)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except: pass
        
        # 1b. Prefer adapter with a default gateway on Windows
        try:
            out = subprocess.check_output(["ipconfig"], encoding="utf-8", errors="ignore")
            blocks = [b for b in out.split("\n\n") if "IPv4" in b]
            import re
            for b in blocks:
                if "Default Gateway" in b:
                    gw = re.findall(r"Default Gateway.*?:\s*(\d+\.\d+\.\d+\.\d+)", b)
                    ip = re.findall(r"IPv4 Address.*?:\s*(\d+\.\d+\.\d+\.\d+)|IPv4-Adresse.*?:\s*(\d+\.\d+\.\d+\.\d+)", b)
                    gw = [g for g in gw if g and not g.startswith("0.0.0.0")]
                    ip_flat = [i for tup in ip for i in tup if i]
                    if gw and ip_flat:
                        cand = ip_flat[0]
                        if not cand.startswith("127.") and not cand.startswith("169.254."):
                            return cand
        except: pass
        
        # 2. Try socket.gethostbyname(hostname)
        try:
            ip = socket.gethostbyname(socket.gethostname())
            if not ip.startswith("127."): return ip
        except: pass
        
        # 3. Iterate interfaces
        try:
            hostname = socket.gethostname()
            all_ips = socket.gethostbyname_ex(hostname)[2]
            for ip in all_ips:
                if not ip.startswith("127.") and not ip.startswith("169.254."):
                    return ip
        except: pass
        
        # 4. Windows ipconfig fallback
        try:
            out = subprocess.check_output(["ipconfig"], encoding="utf-8", errors="ignore")
            import re
            ips = re.findall(r"(?:IPv4 Address.*?:\\s*|IPv4-Adresse.*?:\\s*|IPv4.*?:\\s*)(\\d+\\.\\d+\\.\\d+\\.\\d+)", out)
            candidates = [ip for ip in ips if not ip.startswith("127.") and not ip.startswith("169.254.")]
            if candidates:
                candidates.sort(key=lambda x: 0 if x.startswith("192.168.") else (1 if x.startswith("10.") else (2 if x.startswith("172.") else 3)))
                return candidates[0]
        except: pass
        
        return "127.0.0.1"

    def start(self, use_ngrok=False):
        if self.running: return self.public_url or self.local_url or f"http://localhost:{self.port}"
        
        # Log startup
        try:
            with open("server_startup.log", "w") as f:
                f.write(f"Startup initiated at {datetime.now()}\n")
        except: pass

        # Ensure pyngrok is available if HTTPS requested
        if use_ngrok and not HAS_NGROK:
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "pyngrok"])
                from pyngrok import ngrok as _ngrok, conf as _conf
                globals()["ngrok"] = _ngrok
                globals()["conf"] = _conf
                globals()["HAS_NGROK"] = True
            except Exception as e:
                self.ngrok_error = f"pyngrok install failed: {e}"
                use_ngrok = False
        
        # Kill any existing ngrok processes to be safe, but only if we are about to start a new one.
        if use_ngrok and HAS_NGROK:
            self.log("Attempting to clean up old ngrok processes...")
            try:
                for p in ngrok.get_tunnels():
                    ngrok.disconnect(p.public_url)
                ngrok.kill()
                self.log("Old ngrok processes cleaned up.")
            except Exception as e:
                self.log(f"No old ngrok processes to kill or cleanup failed: {e}")
                pass
                
        self.running = True
        
        # Handler factory to pass 'self' to the handler
        handler = lambda *args, **kwargs: VocaHTTPHandler(self, *args, **kwargs)
        
        # Priority Ports (Add self.port to front if not already there)
        ports_to_try = [self.port, 5050, 8080, 8000, 5000, 8081, 3000]
        # Remove duplicates while preserving order
        ports_to_try = list(dict.fromkeys(ports_to_try))
        
        # First attempt: Try self.port specifically
        default_port = self.port
        
        try:
            # Try to bind directly first - fastest path
            socketserver.TCPServer.allow_reuse_address = True
            self.server = socketserver.ThreadingTCPServer(('0.0.0.0', default_port), handler)
            self.port = default_port
        except OSError as e:
            # Only if bind fails do we try to kill
            self.log(f"Port {default_port} busy ({e}). Attempting to kill old process...")
            if self.kill_process_on_port(default_port):
                time.sleep(0.5)
                try:
                    socketserver.TCPServer.allow_reuse_address = True
                    self.server = socketserver.ThreadingTCPServer(('0.0.0.0', default_port), handler)
                    self.port = default_port
                except OSError:
                    pass 
        
        if not self.server:
            # Fallback loop
            for p in ports_to_try:
                if p == default_port: continue 
                try:
                    socketserver.TCPServer.allow_reuse_address = True
                    self.server = socketserver.ThreadingTCPServer(('0.0.0.0', p), handler)
                    self.port = p
                    break
                except OSError:
                    continue
            
        if not self.server:
            # Last resort: Port 0 (random)
            try:
                socketserver.TCPServer.allow_reuse_address = True
                self.server = socketserver.ThreadingTCPServer(('0.0.0.0', 0), handler)
                self.port = self.server.server_address[1]
                self.log(f"Fallback to random port {self.port}")
            except Exception as e:
                self.log(f"Critical Error: Could not bind any port: {e}")
                self.running = False
                return None
        
        try:
            self.server.daemon_threads = True
            self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.server_thread.start()
            
            self.log(f"Server started on port {self.port}")
            try:
                import subprocess
                rule = f'netsh advfirewall firewall add rule name="VocaAI HTTP {self.port}" dir=in action=allow protocol=TCP localport={self.port} profile=any'
                subprocess.run(["powershell", "-NoProfile", "-Command", rule], capture_output=True, text=True, shell=False)
            except Exception:
                pass
            
            # Get IP - Improved Logic
            self.available_ips = []
            
            # Use improved detection
            primary_ip = self.get_lan_ip()
            if primary_ip:
                self.available_ips.append(primary_ip)
            
            try:
                # Get all interface IPs for the list
                hostname = socket.gethostname()
                all_ips = socket.gethostbyname_ex(hostname)[2]
                
                # Filter IPs
                filtered_ips = []
                for ip in all_ips:
                    if ip.startswith("127."): continue
                    if ip.startswith("169.254."): continue # APIPA
                    filtered_ips.append(ip)
                
                # Sort remaining IPs by preference (192.168 > 10. > 172.)
                filtered_ips.sort(key=lambda x: 0 if x.startswith("192.168.") else (1 if x.startswith("10.") else 2))
                
                # Add others that are not primary
                for ip in filtered_ips:
                    if ip != primary_ip and ip not in self.available_ips:
                        self.available_ips.append(ip)
                    
            except:
                pass
            
            # Supplement from ipconfig
            try:
                out = subprocess.check_output(["ipconfig"], encoding="utf-8", errors="ignore")
                import re
                ips = re.findall(r"(?:IPv4 Address.*?:\\s*|IPv4-Adresse.*?:\\s*|IPv4.*?:\\s*)(\\d+\\.\\d+\\.\\d+\\.\\d+)", out)
                for ip in ips:
                    if ip.startswith("127.") or ip.startswith("169.254."):
                        continue
                    if ip not in self.available_ips:
                        self.available_ips.append(ip)
            except:
                pass
            
            # Fallback
            if not self.available_ips:
                self.available_ips.append("127.0.0.1")

            # Use the first one as default
            local_ip = self.available_ips[0]
                
            self.local_url = f"http://{local_ip}:{self.port}"
            print(f"Web Server (HTTP) started on {self.local_url}")

            # Try to start local HTTPS (self-signed) so mic/camera work on phones
            try:
                https_started = self._try_start_https(local_ip)
                if https_started:
                    self.https_url = f"https://{local_ip}:{self.https_port}"
                    print(f"Web Server (HTTPS) available at {self.https_url}")
                    try:
                        import subprocess
                        rule = f'netsh advfirewall firewall add rule name="VocaAI HTTPS {self.https_port}" dir=in action=allow protocol=TCP localport={self.https_port} profile=any'
                        subprocess.run(["powershell", "-NoProfile", "-Command", rule], capture_output=True, text=True, shell=False)
                    except Exception:
                        pass
            except Exception as e:
                self.log(f"HTTPS start failed: {e}")
            
            # Write success log
            try:
                with open("server_startup.log", "a") as f:
                    f.write(f"Success: {self.local_url}\n")
            except: pass
            
            if use_ngrok and HAS_NGROK and not getattr(self, "ngrok_disabled", False):
                self.log("Starting ngrok tunnel...")
                try:
                    # Apply project-local ngrok config and token
                    try:
                        self._apply_ngrok_config()
                    except Exception as e:
                        self.log(f"Ngrok config apply error: {e}")
                    # Setup local bin path for ngrok to avoid permission issues
                    current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                    bin_dir = os.path.join(current_dir, "bin")
                    if not os.path.exists(bin_dir):
                        os.makedirs(bin_dir)
                    
                    ngrok_candidate = os.path.join(bin_dir, "ngrok.exe")
                    if os.path.exists(ngrok_candidate):
                        self.log(f"Using local ngrok binary at {ngrok_candidate}")
                        conf.get_default().ngrok_path = ngrok_candidate
                    
                    # Optional region override via env (e.g., NGROK_REGION=ap, in, eu, us)
                    try:
                        region = os.environ.get("NGROK_REGION")
                        if region:
                            conf.get_default().region = region
                            self.log(f"Ngrok region set to {region}")
                    except Exception:
                        pass
                    
                    # Force IPv4 to prevent 502 issues on Windows
                    self.log(f"Connecting ngrok to 127.0.0.1:{self.port}...")
                    # Prefer HTTPS public URL by binding TLS; honor preferred hostname if provided
                    connect_kwargs = {"addr": f"127.0.0.1:{self.port}", "bind_tls": True}
                    try:
                        # Env overrides
                        env_host = os.environ.get("NGROK_HOSTNAME") or os.environ.get("NGROK_SUBDOMAIN")
                        pref = self.preferred_hostname or env_host
                        if pref:
                            # If full hostname with domain, use 'hostname'; else try 'subdomain'
                            if "." in pref:
                                connect_kwargs["hostname"] = pref
                            else:
                                connect_kwargs["subdomain"] = pref
                            self.log(f"Requesting preferred hostname: {pref}")
                    except Exception:
                        pass
                    self.ngrok_tunnel = ngrok.connect(**connect_kwargs)
                    self.public_url = self.ngrok_tunnel.public_url
                    self.log(f"Ngrok Tunnel started successfully on {self.public_url}")
                    return self.public_url
                except Exception as e:
                    self.ngrok_error = str(e)
                    self.log(f"Failed to start ngrok: {e}")
                    # Return error string if auth failed
                    msg = str(e).lower()
                    if "auth" in msg or "account" in msg or "token" in msg or "err_ngrok" in msg:
                        self.public_url = "AUTH_REQUIRED"
                        return "AUTH_REQUIRED"
                    # Endpoint already online: kill and retry once
                    if "already online" in msg or "err_ngrok_334" in msg:
                        try:
                            self.log("Existing endpoint detected. Killing all tunnels and retrying...")
                            for p in ngrok.get_tunnels():
                                ngrok.disconnect(p.public_url)
                            ngrok.kill()
                            time.sleep(1)
                            # Retry with TLS-bound https
                            self.ngrok_tunnel = ngrok.connect(addr=f"127.0.0.1:{self.port}", bind_tls=True)
                            self.public_url = self.ngrok_tunnel.public_url
                            self.log(f"Ngrok Tunnel restarted on {self.public_url}")
                            return self.public_url
                        except Exception as e2:
                            self.log(f"Retry failed: {e2}")
                    # Session limits or hard failures: disable ngrok for this run
                    if "limited to 3 simultaneous" in msg or "err_ngrok_108" in msg or "failed to start ngrok" in msg:
                        self.ngrok_disabled = True
                    # Fallback to local
            
            # Fallback: try Cloudflare Quick Tunnel if ngrok is not enabled/available or failed
            try:
                if (use_ngrok and (not HAS_NGROK or self.public_url is None or self.public_url == "AUTH_REQUIRED")) or getattr(self, "ngrok_disabled", False):
                    self.log("Trying Cloudflare quick tunnel as fallback...")
                    if self._start_cloudflared():
                        self.public_url = self.cfd_url
                        self.log(f"Cloudflared Tunnel started on {self.public_url}")
                        return self.public_url
            except Exception as e:
                self.cfd_error = str(e)
                self.log(f"Cloudflared fallback error: {e}")
            
            return self.local_url
        except Exception as e:
            print(f"Failed to start web server: {e}")
            import traceback
            traceback.print_exc()
            self.running = False
            return None
    
    def try_upnp_public(self):
        try:
            try:
                import miniupnpc as upnp
            except Exception:
                return None
            u = upnp.UPnP()
            u.discoverdelay = 2000
            n = u.discover()
            if n <= 0:
                return None
            u.selectigd()
            ext_ip = u.externalipaddress()
            # Prefer HTTPS port if available (for browser mic/camera)
            if getattr(self, 'https_server', None) and getattr(self, 'https_port', None):
                internal_port = self.https_port
                ext_port = self.https_port
                scheme = "https"
            else:
                internal_port = self.port
                ext_port = self.port
                scheme = "http"
            try:
                u.deleteportmapping(ext_port, 'TCP')
            except Exception:
                pass
            r = u.addportmapping(ext_port, 'TCP', u.lanaddr, internal_port, 'VocaAI', '')
            if not r:
                return None
            self.upnp_mapped = True
            self.upnp_external_ip = ext_ip
            self.upnp_external_port = ext_port
            return f"{scheme}://{ext_ip}:{ext_port}"
        except Exception:
            return None

    def _apply_ngrok_config(self):
        """Apply project-local ngrok settings so auth token detection is reliable."""
        if not HAS_NGROK:
            return False
        proj_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        bin_dir = os.path.join(proj_root, "bin")
        try:
            os.makedirs(bin_dir, exist_ok=True)
        except Exception:
            pass
        # Configure binary path if present
        ngrok_candidate = os.path.join(bin_dir, "ngrok.exe")
        try:
            if os.path.exists(ngrok_candidate):
                conf.get_default().ngrok_path = ngrok_candidate
        except Exception:
            pass
        # Configure custom config path
        cfg_path = os.path.join(bin_dir, "ngrok.yml")
        try:
            conf.get_default().config_path = cfg_path
        except Exception:
            pass
        # Apply token from environment or file if present
        try:
            token = os.environ.get("NGROK_AUTHTOKEN")
            if not token and os.path.exists(cfg_path):
                try:
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        import re
                        m = re.search(r"authtoken\s*:\s*([^\s]+)", content, re.IGNORECASE)
                        if m:
                            token = m.group(1).strip().strip("'").strip('"')
                except Exception:
                    token = None
            if token:
                conf.get_default().auth_token = token
                return True
        except Exception:
            pass
        return False

    def _ensure_self_signed_cert(self, ips):
        try:
            if os.path.exists(self.cert_path) and os.path.exists(self.key_path):
                return True
            os.makedirs(self.cert_dir, exist_ok=True)
            try:
                from cryptography import x509
                from cryptography.x509.oid import NameOID
                from cryptography.hazmat.primitives.asymmetric import rsa
                from cryptography.hazmat.primitives import serialization, hashes
                from cryptography.hazmat.primitives.serialization import NoEncryption, Encoding, PrivateFormat
            except Exception:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "cryptography"])
                from cryptography import x509
                from cryptography.x509.oid import NameOID
                from cryptography.hazmat.primitives.asymmetric import rsa
                from cryptography.hazmat.primitives import serialization, hashes
                from cryptography.hazmat.primitives.serialization import NoEncryption, Encoding, PrivateFormat

            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, u"Voca Local Server")])

            alt_names = [x509.DNSName(u"localhost")]
            for ip in ips:
                try:
                    alt_names.append(x509.IPAddress(socket.inet_aton(ip) and None))  # will raise
                except Exception:
                    try:
                        from ipaddress import ip_address
                        alt_names.append(x509.IPAddress(ip_address(ip)))
                    except Exception:
                        pass
            san = x509.SubjectAlternativeName(alt_names)

            cert = (
                x509.CertificateBuilder()
                .subject_name(name)
                .issuer_name(name)
                .public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(datetime.utcnow())
                .not_valid_after(datetime.utcnow().replace(year=datetime.utcnow().year + 1))
                .add_extension(san, critical=False)
                .sign(key, hashes.SHA256())
            )

            with open(self.key_path, "wb") as f:
                f.write(
                    key.private_bytes(
                        Encoding.PEM,
                        PrivateFormat.TraditionalOpenSSL,
                        NoEncryption(),
                    )
                )
            with open(self.cert_path, "wb") as f:
                f.write(cert.public_bytes(Encoding.PEM))
            return True
        except Exception as e:
            self.log(f"Self-signed cert generation failed: {e}")
            return False

    def _try_start_https(self, local_ip):
        try:
            # Generate certificate if missing
            if not self._ensure_self_signed_cert(self.available_ips or [local_ip, "127.0.0.1"]):
                return False
            import ssl
            handler = lambda *args, **kwargs: VocaHTTPHandler(self, *args, **kwargs)

            # Try preferred HTTPS ports
            https_ports = [self.https_port, 5443, 5051, 8443]
            https_ports = list(dict.fromkeys(https_ports))
            self.https_server = None
            for p in https_ports:
                try:
                    socketserver.TCPServer.allow_reuse_address = True
                    srv = socketserver.ThreadingTCPServer(('0.0.0.0', p), handler)
                    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                    ctx.load_cert_chain(certfile=self.cert_path, keyfile=self.key_path)
                    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
                    self.https_server = srv
                    self.https_port = p
                    break
                except OSError:
                    continue
            if not self.https_server:
                return False
            self.https_server.daemon_threads = True
            self.https_thread = threading.Thread(target=self.https_server.serve_forever, daemon=True)
            self.https_thread.start()
            return True
        except Exception as e:
            self.log(f"HTTPS init error: {e}")
            return False

    def stop(self):
        self.running = False
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception as e:
                print(f"Server shutdown error: {e}")
            self.server = None
        if self.https_server:
            try:
                self.https_server.shutdown()
                self.https_server.server_close()
            except Exception as e:
                print(f"HTTPS server shutdown error: {e}")
            self.https_server = None
        
        if self.ngrok_tunnel:
            try:
                ngrok.disconnect(self.public_url)
                ngrok.kill()
                self.ngrok_tunnel = None
                self.public_url = None
            except:
                pass
        if self.cfd_process:
            try:
                self.cfd_process.terminate()
            except Exception:
                pass
            self.cfd_process = None
            self.cfd_url = None
        try:
            if self.upnp_mapped:
                import miniupnpc as upnp
                u = upnp.UPnP()
                u.discoverdelay = 1000
                u.discover()
                u.selectigd()
                if self.upnp_external_port:
                    try:
                        u.deleteportmapping(self.upnp_external_port, 'TCP')
                    except Exception:
                        pass
        except Exception:
            pass

    def broadcast_update(self, event_type, data):
        """Send update to all connected web clients"""
        if event_type == "TRANSCRIPT":
            self.latest_transcript = data
        elif event_type == "VOICE":
            self.latest_voice = data
            
        msg = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
        
        # Clean up dead clients
        dead_clients = []
        for q in self.clients:
            try:
                q.put(msg)
            except:
                dead_clients.append(q)
                
        for dc in dead_clients:
            if dc in self.clients:
                self.clients.remove(dc)

class VocaHTTPHandler(http.server.BaseHTTPRequestHandler):
    def __init__(self, app_server, *args, **kwargs):
        self.app_server = app_server
        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):
        pass # Suppress logging

    def do_GET(self):
        try:
            self.app_server.log(f"GET {self.path} from {self.client_address[0]}")
        except Exception:
            pass
        
        
        if self.path == '/ping':
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"pong")
            return

        if self.path == '/':
            try:
                html_content = self.get_html().encode('utf-8')
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(html_content)))
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(html_content)
            except Exception as e:
                print(f"Error serving HTML: {e}")
                self.send_error(500, "Internal Server Error")
        
        elif self.path == '/manifest.json':
            self.send_response(200)
            self.send_header('Content-type', 'application/manifest+json')
            self.end_headers()
            manifest = {
                "name": "VocaAI Mobile",
                "short_name": "VocaAI",
                "start_url": "/",
                "display": "standalone",
                "background_color": "#121212",
                "theme_color": "#121212",
                "icons": [
                    {
                        "src": "/logo.svg",
                        "sizes": "192x192",
                        "type": "image/svg+xml"
                    },
                    {
                        "src": "/logo.svg",
                        "sizes": "512x512",
                        "type": "image/svg+xml"
                    }
                ]
            }
            self.wfile.write(json.dumps(manifest).encode('utf-8'))
            
        elif self.path == '/logo.svg':
            self.send_response(200)
            self.send_header('Content-type', 'image/svg+xml')
            self.end_headers()
            svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><circle cx="256" cy="256" r="256" fill="#1e1e1e"/><path d="M256 64c106 0 192 86 192 192s-86 192-192 192S64 362 64 256 150 64 256 64zm0 44c-81.7 0-148 66.3-148 148s66.3 148 148 148 148-66.3 148-148-66.3-148-148-148z" fill="#00FFD1"/></svg>"""
            self.wfile.write(svg.encode('utf-8'))
            
        elif self.path == '/app.js':
            js = self.get_app_js().encode('utf-8')
            self.send_response(200)
            self.send_header('Content-type', 'application/javascript; charset=utf-8')
            self.send_header('Content-Length', str(len(js)))
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(js)
            
        elif self.path == '/events':
            # SSE Endpoint
            self.send_response(200)
            self.send_header('Content-type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            import queue
            q = queue.Queue()
            self.app_server.clients.append(q)
            
            # Send initial state
            try:
                init_msg = f"event: INIT\ndata: {json.dumps({'transcript': self.app_server.latest_transcript, 'voice': self.app_server.latest_voice})}\n\n"
                self.wfile.write(init_msg.encode('utf-8'))
                self.wfile.flush()
                
                while self.app_server.running:
                    msg = q.get()
                    self.wfile.write(msg.encode('utf-8'))
                    self.wfile.flush()
            except Exception:
                pass
            finally:
                if q in self.app_server.clients:
                    self.app_server.clients.remove(q)

    def do_POST(self):
        if self.path == '/log':
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                print(f"MOBILE LOG: {post_data.decode('utf-8')}")
                self.send_response(200)
                self.end_headers()
            except:
                pass
                
        elif self.path == '/upload_frame':
            try:
                content_length = int(self.headers['Content-Length'])
                # Read raw binary data (expecting JPEG bytes or base64 json)
                # Let's assume JSON with base64 for cleaner handling or raw bytes
                # For speed, raw bytes is better, but JSON is easier to debug
                # Let's use JSON with base64
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                
                if 'image' in data:
                    import base64
                    import numpy as np
                    import cv2
                    
                    # Remove header if present (data:image/jpeg;base64,)
                    img_data = data['image']
                    if ',' in img_data:
                        img_data = img_data.split(',')[1]
                        
                    # Decode
                    img_bytes = base64.b64decode(img_data)
                    np_arr = np.frombuffer(img_bytes, np.uint8)
                    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                    
                    if frame is not None:
                        with self.app_server.frame_lock:
                            self.app_server.latest_frame = frame
                            self.app_server.remote_sign_active = True
                            self.app_server.last_frame_time = time.time()
                            
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK")
            except Exception as e:
                print(f"Frame Upload Error: {e}")
                self.send_response(400)
                self.end_headers()

        elif self.path == '/stop_camera':
            self.app_server.remote_sign_active = False
            self.app_server.latest_frame = None
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

        elif self.path == '/send':
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                print(f"Web: Received POST data: {post_data[:50]}...")
                
                data = json.loads(post_data.decode('utf-8'))
                if self.app_server.message_callback:
                    try:
                        self.app_server.message_callback(data)
                    except Exception as cb_err:
                        print(f"Web: message_callback error (main app): {cb_err}")
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok"}).encode('utf-8'))
            except Exception as e:
                print(f"Web POST Error: {e}")
                self.send_response(400)
                self.end_headers()

    def get_html(self):
        html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta name="theme-color" content="#121212">
    <title>VocaAI Mobile (v2)</title>
    
    <!-- PWA Settings -->
    <link rel="manifest" href="/manifest.json">
    <link rel="icon" type="image/svg+xml" href="/logo.svg">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="VocaAI">
    <link rel="apple-touch-icon" href="/logo.svg">

    <style>
        /* CSS Reset and Variables */
        :root {
            --bg-color: #121212;
            --card-bg: #1e1e1e;
            --text-color: #e0e0e0;
            --accent-color: #00FFD1;
            --primary-color: #0078D4;
        }
        
        body.light-theme {
            --bg-color: #f5f5f5;
            --card-bg: #ffffff;
            --text-color: #333333;
            --accent-color: #0078D4;
        }
        body.light-theme .chip {
            background: #eee;
            color: #333;
            border-color: #ccc;
        }
        body.light-theme .chip:active {
            color: #fff;
        }
        
        * { box-sizing: border-box; }
        
        html, body {
            margin: 0;
            padding: 0;
            width: 100%;
            height: 100%;
            background-color: var(--bg-color);
            color: var(--text-color);
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            overflow: hidden; /* Prevent scrolling on body, scroll main instead */
        }

        body {
            display: flex;
            flex-direction: column;
            /* Fallback for browsers not supporting dvh */
            height: 100vh;
            /* Dynamic Viewport Height for modern mobile browsers */
            height: 100dvh;
        }

        /* Header */
        header {
            background-color: var(--card-bg);
            padding: 10px 15px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid #333;
            box-shadow: 0 2px 4px rgba(0,0,0,0.2);
            z-index: 10;
        }
        
        h1 { margin: 0; color: var(--accent-color); font-size: 1.1rem; flex: 1; text-align: center; }
        .header-btns { display: flex; gap: 8px; align-items: center; }
        .hdr-btn {
            background: none; border: 1px solid #444; color: #aaa; border-radius: 8px;
            padding: 6px 10px; font-size: .85rem; cursor: pointer;
        }
        
        .status-bar { 
            font-size: 0.8rem; 
            color: #888; 
            margin-top: 5px; 
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
        }
        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background-color: #444;
        }
        .connected .status-dot { background-color: #4CAF50; box-shadow: 0 0 5px #4CAF50; }
        .disconnected .status-dot { background-color: #f44336; }

        /* Quick Phrases */
        .quick-phrases {
            display: flex;
            gap: 10px;
            overflow-x: auto;
            padding-bottom: 5px;
            -webkit-overflow-scrolling: touch;
            scrollbar-width: none; /* Firefox */
        }
        .quick-phrases::-webkit-scrollbar { display: none; }
        
        .chip {
            background: #333;
            color: #eee;
            border: 1px solid #444;
            padding: 8px 16px;
            border-radius: 20px;
            white-space: nowrap;
            font-size: 0.9rem;
            cursor: pointer;
            transition: all 0.2s;
            user-select: none;
        }
        .chip:active {
            background: var(--accent-color);
            color: #000;
            transform: scale(0.95);
        }

        /* Theme Toggle */
        .theme-toggle {
            background: none;
            border: none;
            color: #aaa;
            font-size: 1.2rem;
            padding: 5px;
            cursor: pointer;
            width: auto;
            height: auto;
            box-shadow: none;
        }

        /* Main Content Area */
        main {
            flex: 1;
            overflow-y: auto;
            padding: 15px;
            display: flex;
            flex-direction: column;
            gap: 15px;
            -webkit-overflow-scrolling: touch;
        }
        
        .card { 
            background: var(--card-bg); 
            border-radius: 12px; 
            padding: 15px; 
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
            border: 1px solid #333;
            display: flex;
            flex-direction: column;
        }
        
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
            border-bottom: 1px solid #2a2a2a;
            padding-bottom: 8px;
        }
        
        .label { 
            font-size: 0.75rem; 
            color: #aaa; 
            text-transform: uppercase; 
            letter-spacing: 1px; 
            font-weight: bold; 
        }
        
        .content { 
            font-size: 1.1rem; 
            line-height: 1.5; 
            min-height: 1.5em; 
            word-wrap: break-word; 
        }
        
        #transcript { color: #ffffff; }
        #voice { color: var(--accent-color); }

        /* Footer / Input Area */
        .footer {
            background: var(--card-bg);
            padding: 10px 15px;
            padding-bottom: max(12px, env(safe-area-inset-bottom)); /* iOS Safe Area */
            border-top: 1px solid #333;
            display: flex;
            gap: 10px;
            align-items: center;
            z-index: 10;
            position: sticky; /* Keep visible when content scrolls */
            bottom: 0;
            left: 0;
            right: 0;
        }
        
        input[type="text"] { 
            flex: 1; 
            padding: 12px 15px; 
            border-radius: 25px; 
            border: 1px solid #444; 
            background: #2a2a2a; 
            color: white; 
            outline: none; 
            font-size: 16px; /* Prevents zoom on iOS input focus */
            -webkit-appearance: none;
        }
        
        input[type="text"]:focus { 
            border-color: var(--accent-color); 
            background: #333; 
        }
        
        button { 
            background: var(--primary-color); 
            color: white; 
            border: none; 
            width: 48px;
            height: 48px;
            border-radius: 50%; 
            font-weight: bold; 
            cursor: pointer; 
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.2rem;
            box-shadow: 0 2px 5px rgba(0,0,0,0.3);
            flex-shrink: 0;
            -webkit-tap-highlight-color: transparent;
        }
        
        button:active { transform: scale(0.95); opacity: 0.9; }
        
        .mic-btn { 
            background: #2a2a2a; 
            border: 1px solid #444; 
            color: var(--accent-color); 
            margin-right: 5px; 
        }
        .send-btn {
            background: var(--primary-color);
        }
        @media (max-width: 360px) {
            /* Ensure send button remains visible alongside input on very small screens */
            input[type="text"] { font-size: 15px; padding: 10px 14px; }
            button { width: 44px; height: 44px; }
        }
        @media (max-width: 420px) {
            .footer { gap: 6px; }
            button { width: 44px; height: 44px; }
            #langToggle, #speakToggle { padding: 4px 6px; font-size: 10px; }
        }
        
        .mic-btn.listening { 
            background: #f44336; 
            color: white; 
            border-color: #f44336; 
            animation: pulse 1.5s infinite; 
        }

        .sign-btn {
            background: #2a2a2a;
            border: 1px solid #444;
            color: #ff9800; /* Orange for sign */
            margin-right: 5px;
        }
        .sign-btn.active {
            background: #ff9800;
            color: white;
            border-color: #ff9800;
            animation: pulse-orange 1.5s infinite;
        }
        @keyframes pulse-orange {
            0% { box-shadow: 0 0 0 0 rgba(255, 152, 0, 0.4); }
            70% { box-shadow: 0 0 0 10px rgba(255, 152, 0, 0); }
            100% { box-shadow: 0 0 0 0 rgba(255, 152, 0, 0); }
        }

        #camera-preview {
            position: fixed;
            bottom: 70px;
            right: 15px;
            width: 120px;
            height: 160px;
            background: #000;
            border: 2px solid #333;
            border-radius: 8px;
            z-index: 100;
            display: none;
            object-fit: cover;
            transform: scaleX(-1); /* Mirror effect for selfie, maybe remove for environment */
        }
        
        @keyframes pulse {
            0% { box-shadow: 0 0 0 0 rgba(244, 67, 54, 0.4); }
            70% { box-shadow: 0 0 0 10px rgba(244, 67, 54, 0); }
            100% { box-shadow: 0 0 0 0 rgba(244, 67, 54, 0); }
        }

        /* Loading Overlay */
        #loader {
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: #121212;
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 9999;
            transition: opacity 0.5s;
        }
        .spinner {
            width: 40px; height: 40px;
            border: 4px solid #333;
            border-top: 4px solid var(--accent-color);
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }

    </style>
</head>
<body>
    <div id="loader" style="flex-direction: column; gap: 20px;">
        <div class="spinner"></div>
        <button onclick="document.getElementById('loader').style.display='none'" style="background: #333; color: white; border: 1px solid #555; padding: 8px 16px; border-radius: 20px; font-size: 14px; cursor: pointer;">
            Tap to Cancel Loading
        </button>
    </div>
    
    <script>
        // CRITICAL: Immediate Loader Removal Logic
        // This script is placed here to ensure it runs even if the main app script fails later.
        (function() {
            function forceRemoveLoader() {
                var loader = document.getElementById('loader');
                if (loader) {
                    loader.style.opacity = '0';
                    setTimeout(function() {
                        if (loader) loader.style.display = 'none';
                    }, 500);
                }
            }
            // Failsafe 1: Remove after 1.5s
            setTimeout(forceRemoveLoader, 1500);
            
            // Failsafe 2: Remove on window load
            window.addEventListener('load', forceRemoveLoader);
            
            // Failsafe 3: Global Error Handler for Startup
            window.onerror = function(msg, url, line, col, error) {
                try {
                    console.error("Startup Error:", msg, "at", url, line + ":" + col, error && error.stack);
                } catch(_) {}
                forceRemoveLoader();
                
                // Show visible error
                var errDiv = document.createElement('div');
                errDiv.style.cssText = "position:fixed;top:0;left:0;right:0;background:red;color:white;padding:10px;z-index:10000;font-size:12px;";
                var loc = (url ? " at " + url : "") + (line ? " line " + line : "") + (col ? ":" + col : "");
                errDiv.innerHTML = "<strong>Error:</strong> " + msg + loc;
                document.body.appendChild(errDiv);
                
                return false;
            };
        })();
    </script>

    <header>
        <div class="header-btns">
            <button class="theme-toggle" onclick="toggleTheme()">🌙</button>
            <button class="hdr-btn" onclick="reconnect()">↻</button>
            <button class="hdr-btn" onclick="openHelp()">?</button>
        </div>
        <h1>VocaAI Mobile</h1>
        <div id="status" class="status-bar">
            <span class="status-dot"></span>
            <span id="status-text">Connecting...</span>
        </div>
    </header>
    
    <main>
        <div class="card">
            <div class="card-header">
                <span class="label">Quick Talk (AAC)</span>
            </div>
            <div class="quick-phrases">
                <div class="chip" data-text="Hello!">👋 Hello</div>
                <div class="chip" data-text="Yes">✅ Yes</div>
                <div class="chip" data-text="No">❌ No</div>
                <div class="chip" data-text="Thank You">🙏 Thanks</div>
                <div class="chip" data-text="Please wait">✋ Wait</div>
                <div class="chip" data-text="Help needed">🆘 Help</div>
                <div class="chip" data-text="I cannot hear you">🦻 Can't Hear</div>
            </div>
        </div>

        <div class="card">
            <div class="card-header">
                <span class="label">PC Sign Translation</span>
            </div>
            <div id="transcript" class="content">Waiting for signs...</div>
        </div>
        
        <div class="card">
            <div class="card-header">
                <span class="label">My Voice Output</span>
            </div>
            <div id="voice" class="content">Type or speak below...</div>
            <div id="historyList" class="content" style="margin-top:10px;font-size:.95rem;"></div>
        </div>
    </main>
    
    <video id="camera-preview" autoplay playsinline muted></video>
    <canvas id="frame-canvas" style="display:none;"></canvas>

    <div class="footer">
        <button class="sign-btn" id="signBtn" onclick="toggleSign()">📷</button>
        <button class="switch-btn" id="switchBtn" onclick="switchCamera()" style="display:none; background: #444; margin-right: 5px;">🔄</button>
        <button class="mic-btn" id="micBtn" onclick="toggleMic()">🎤</button>
        <button id="langToggle" style="background:#333;color:#fff;border:none;border-radius:16px;padding:6px 10px;font-size:11px;margin:0 4px;">ML</button>
        <input type="text" id="msgInput" placeholder="Message..." onkeypress="handleKeyPress(event)" autocomplete="off">
        <button id="speakToggle" style="background:#333;color:#fff;border:none;border-radius:16px;padding:6px 10px;font-size:11px;margin:0 4px;">🔈</button>
        <button class="send-btn" onclick="sendMessage()" aria-label="Send">➤</button>
    </div>

    <script src="/app.js"></script>
</body>
</html>
"""
        return html.replace("<title>VocaAI Mobile (v2)</title>", f"<title>VocaAI Mobile (v2.2 - {datetime.now().strftime('%H:%M:%S')})</title>")

    def set_preferred_hostname(self, hostname):
        try:
            if isinstance(hostname, str):
                hostname = hostname.strip()
                self.preferred_hostname = hostname if hostname else None
        except Exception:
            self.preferred_hostname = None

    def _start_cloudflared(self):
        try:
            proj_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            bin_dir = os.path.join(proj_root, "bin")
            try:
                os.makedirs(bin_dir, exist_ok=True)
            except Exception:
                pass
            cfd_exe = os.path.join(bin_dir, "cloudflared.exe")
            if not os.path.exists(cfd_exe):
                self.log("Downloading cloudflared binary...")
                try:
                    # Use PowerShell to download the latest Windows AMD64 binary
                    url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
                    cmd = ["powershell", "-NoProfile", "-Command", f"Invoke-WebRequest -Uri '{url}' -OutFile '{cfd_exe}'"]
                    subprocess.run(cmd, check=True, capture_output=True, text=True, shell=False)
                except Exception as e:
                    self.cfd_error = f"Download failed: {e}"
                    self.log(self.cfd_error)
                    return False
            # Start quick tunnel
            self.log("Starting Cloudflare quick tunnel...")
            self.cfd_process = subprocess.Popen(
                [cfd_exe, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{self.port}"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True
            )
            # Parse URL from output
            start_time = time.time()
            while time.time() - start_time < 20:
                try:
                    line = self.cfd_process.stdout.readline()
                    if not line:
                        time.sleep(0.2)
                        continue
                    lower = line.lower()
                    if "trycloudflare.com" in lower:
                        # Extract https URL
                        import re
                        m = re.search(r"(https://[a-z0-9\-\.]+trycloudflare\.com)", line, re.IGNORECASE)
                        if m:
                            self.cfd_url = m.group(1)
                            return True
                except Exception:
                    break
            self.cfd_error = "Cloudflared did not provide a URL in time."
            self.log(self.cfd_error)
            return False
        except Exception as e:
            self.cfd_error = str(e)
            self.log(f"Cloudflared error: {e}")
            return False

    def start_cloudflare(self):
        """
        Explicitly start Cloudflare quick tunnel and return URL.
        Ensures the local HTTP server is running first.
        """
        try:
            if not self.running:
                # Start locally without ngrok
                started = self.start(use_ngrok=False)
                if not started:
                    return None
            if self._start_cloudflared():
                self.public_url = self.cfd_url
                return self.public_url
            return None
        except Exception as e:
            self.cfd_error = str(e)
            return None
    
    def start_cloudflare_named(self, hostname):
        try:
            if not hostname:
                return None
            proj_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            bin_dir = os.path.join(proj_root, "bin")
            os.makedirs(bin_dir, exist_ok=True)
            cfd_exe = os.path.join(bin_dir, "cloudflared.exe")
            if not os.path.exists(cfd_exe):
                url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
                cmd = ["powershell", "-NoProfile", "-Command", f"Invoke-WebRequest -Uri '{url}' -OutFile '{cfd_exe}'"]
                subprocess.run(cmd, check=True, capture_output=True, text=True, shell=False)
            if not self.running:
                started = self.start(use_ngrok=False)
                if not started:
                    return None
            if self.cfd_process:
                try:
                    self.cfd_process.terminate()
                except Exception:
                    pass
            self.cfd_process = subprocess.Popen(
                [cfd_exe, "tunnel", "--no-autoupdate", "--hostname", hostname, "--url", f"http://127.0.0.1:{self.port}"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True
            )
            self.public_url = f"https://{hostname}"
            return self.public_url
        except Exception as e:
            self.cfd_error = str(e)
            return None
    
    def cloudflare_login(self):
        try:
            proj_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            bin_dir = os.path.join(proj_root, "bin")
            os.makedirs(bin_dir, exist_ok=True)
            cfd_exe = os.path.join(bin_dir, "cloudflared.exe")
            if not os.path.exists(cfd_exe):
                url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
                cmd = ["powershell", "-NoProfile", "-Command", f"Invoke-WebRequest -Uri '{url}' -OutFile '{cfd_exe}'"]
                subprocess.run(cmd, check=True, capture_output=True, text=True, shell=False)
            p = subprocess.Popen([cfd_exe, "tunnel", "login"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            opened = False
            url_found = None
            start_t = time.time()
            while time.time() - start_t < 15:
                try:
                    line = p.stdout.readline()
                    if not line:
                        time.sleep(0.2)
                        continue
                    if "http" in line or "https" in line:
                        import re
                        m = re.search(r"(https?://[^\s]+)", line)
                        if m:
                            url_found = m.group(1)
                            try:
                                import webbrowser
                                webbrowser.open(url_found)
                                opened = True
                            except Exception:
                                pass
                            break
                except Exception:
                    break
            if not opened and url_found:
                try:
                    import webbrowser
                    webbrowser.open(url_found)
                    opened = True
                except Exception:
                    pass
            return True
        except Exception as e:
            self.cfd_error = str(e)
            return False

    def get_app_js(self):
        return """
// ES5-compatible app.js
(function(){
  var isSecure = (window.location.protocol === 'https:' ||
                  window.location.hostname === 'localhost' ||
                  window.location.hostname === '127.0.0.1');

  function showSecureContextWarning(feature) {
    var msg = feature + " requires a secure connection.\\n\\n" +
              "Use the Internet link (HTTPS via ngrok) or enable the Chrome flag:\\n" +
              "chrome://flags/#unsafely-treat-insecure-origin-as-secure\\n\\n" +
              "Then add your local IP and relaunch.";
    try { alert(msg); } catch(e) { console.warn("Secure context warning:", msg); }
  }

  if (!window.sendMessage) window.sendMessage = function(){};
  if (!window.sendQuickPhrase) window.sendQuickPhrase = function(){};
  if (!window.handleKeyPress) window.handleKeyPress = function(){};
  if (!window.toggleSign) window.toggleSign = function(){};
  if (!window.switchCamera) window.switchCamera = function(){};

  var statusContainer = document.getElementById('status');
  var statusText = document.getElementById('status-text');
  var transcriptEl = document.getElementById('transcript');
  var voiceEl = document.getElementById('voice');
  var inputEl = document.getElementById('msgInput');
  var micBtn = document.getElementById('micBtn');
  var langToggle = document.getElementById('langToggle');
  var speakToggle = document.getElementById('speakToggle');
  var historyList = document.getElementById('historyList');

  var recognition = null;
  var speechLang = 'ml-IN';
  var speakEnabled = true;

  function applySpeechLang() {
    if (recognition) {
      try { recognition.lang = speechLang; } catch(e) {}
    }
    if (langToggle) {
      try { langToggle.textContent = (speechLang === 'ml-IN' ? 'ML' : 'EN'); } catch(e) {}
    }
  }
  if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
    var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    applySpeechLang();
    recognition.onstart = function() { micBtn.classList.add('listening'); inputEl.placeholder = "Listening..."; };
    recognition.onend = function() { micBtn.classList.remove('listening'); inputEl.placeholder = "Message..."; };
    recognition.onresult = function(event) {
      var text = event.results[0][0].transcript;
      inputEl.value = text;
      sendMessage();
    };
    recognition.onerror = function(event) {
      try { console.error("Speech recognition error", event.error); } catch(_) {}
      micBtn.classList.remove('listening');
      if (!isSecure && (event.error === 'not-allowed' || event.error === 'service-not-allowed')) {
        showSecureContextWarning("Microphone");
      }
    };
  } else {
    try {
      if (micBtn) {
        micBtn.style.opacity = '0.6';
        micBtn.style.cursor = 'not-allowed';
        micBtn.title = isSecure
          ? 'Speech Recognition not supported in this browser. Use typing.'
          : 'Microphone requires HTTPS. Use the Internet link.';
      }
    } catch(_) {}
  }

  window.toggleMic = function() {
    if (!recognition) {
      if (!isSecure) showSecureContextWarning("Microphone");
      else alert("Speech Recognition not supported in this browser.");
      return;
    }
    if (micBtn.classList.contains('listening')) recognition.stop();
    else {
      try { recognition.start(); }
      catch(e) {
        try { console.error(e); } catch(_) {}
        if (!isSecure) showSecureContextWarning("Microphone");
        else alert("Microphone error: " + e.message);
      }
    }
  };

  if (langToggle) {
    langToggle.addEventListener('click', function(){
      speechLang = (speechLang === 'ml-IN') ? 'en-US' : 'ml-IN';
      applySpeechLang();
    });
  }
  if (speakToggle) {
    speakToggle.addEventListener('click', function(){
      speakEnabled = !speakEnabled;
      try { speakToggle.textContent = speakEnabled ? '🔈' : '🔇'; } catch(e){}
    });
  }

  function connectSSE() {
    var evtSource = new EventSource("/events");
    evtSource.onmessage = function(e) { };
    evtSource.addEventListener("INIT", function(e) {
      try {
        var data = e.data;
        try { data = JSON.parse(e.data); } catch(_) { return; }
        if (data && data.transcript !== "Waiting...") transcriptEl.innerText = data.transcript;
        if (data && data.voice !== "Listening...") voiceEl.innerText = data.voice;
        statusText.innerText = "Connected - Live";
        statusContainer.className = "status-bar connected";
      } catch(err) {}
    });
    evtSource.addEventListener("TRANSCRIPT", function(e) {
      try {
        var data = e.data;
        try { data = JSON.parse(e.data); } catch(_) {}
        transcriptEl.innerText = (typeof data === 'string') ? data : (data && (data.text || data.transcript)) || String(data);
        if (navigator.vibrate) navigator.vibrate(50);
      } catch(err) {}
    });
    evtSource.addEventListener("VOICE", function(e) {
      try {
        var data = e.data;
        try { data = JSON.parse(e.data); } catch(_) {}
        var txt = (typeof data === 'string') ? data : (data && (data.text || data.voice)) || String(data);
        voiceEl.innerText = txt;
        appendHistory('Voice', txt);
        try { if (speakEnabled && window.speechSynthesis) { var u = new SpeechSynthesisUtterance(txt); u.lang = speechLang; speechSynthesis.speak(u); } } catch(_){}
      } catch(err) {}
    });
    evtSource.onerror = function() {
      statusText.innerText = "Reconnecting...";
      statusContainer.className = "status-bar disconnected";
      evtSource.close();
      setTimeout(connectSSE, 3000);
    };
  }
  window.reconnect = function(){ try { connectSSE(); showToast('Reconnecting...'); } catch(e){} };
  window.openHelp = function(){
    try {
      var msg = 'Tips:\\n\\n- Use the camera (📷) to share sign frames.\\n- Use 🎤 to dictate a message.\\n- Tap chips to quick-send common phrases.\\n- If mic/camera fails on local Wi-Fi, use Internet link (HTTPS).';
      alert(msg);
    } catch(e){}
  };

  window.sendMessage = function() {
    var text = (inputEl && inputEl.value) ? inputEl.value.replace(/^\\s+|\\s+$/g, '') : '';
    if (!text) return;
    fetch('/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'ngrok-skip-browser-warning': 'true' },
      body: JSON.stringify({ type: 'VOICE', content: text })
    })
    .then(function(res){ if (res.ok) { inputEl.value = ''; voiceEl.innerText = text; appendHistory('Me', text); try { if (speakEnabled && window.speechSynthesis) { var u = new SpeechSynthesisUtterance(text); u.lang = speechLang; speechSynthesis.speak(u); } } catch(_){} } })
    .catch(function(err){ try { console.error(err); } catch(_) {} });
  };
  function showToast(t){
    try{
      var el = document.createElement('div');
      el.style.cssText = 'position:fixed;bottom:80px;left:50%;transform:translateX(-50%);background:#333;color:#fff;padding:8px 12px;border-radius:16px;font-size:12px;z-index:9999;box-shadow:0 2px 6px rgba(0,0,0,.3)';
      el.textContent = t;
      document.body.appendChild(el);
      setTimeout(function(){ try{ el.remove(); }catch(_){ el.style.display='none'; } }, 1600);
    }catch(_){}
  }
  function appendHistory(who, text){
    try{
      var ts = new Date();
      var hh = String(ts.getHours()).padStart(2,'0');
      var mm = String(ts.getMinutes()).padStart(2,'0');
      var div = document.createElement('div');
      div.style.cssText = 'margin:6px 0;padding:8px;border-radius:8px;background:#1b1b1b;border:1px solid #2a2a2a';
      div.innerHTML = '<span style=\"color:#888;font-size:.8rem;margin-right:6px;\">'+hh+':'+mm+'</span><strong>'+who+':</strong> '+text;
      historyList.appendChild(div);
      try { historyList.parentElement.scrollTop = historyList.parentElement.scrollHeight; } catch(_){}
    }catch(_){}
  }

  window.handleKeyPress = function(e) { if (e.key === 'Enter') window.sendMessage(); };

  var signBtn = document.getElementById('signBtn');
  var switchBtn = document.getElementById('switchBtn');
  var videoEl = document.getElementById('camera-preview');
  var canvasEl = document.getElementById('frame-canvas');
  var signInterval = null;
  var videoStream = null;
  var currentFacingMode = 'user';
  var currentDeviceId = null;
  var frontDeviceId = null;
  var backDeviceId = null;

  if (navigator.mediaDevices === undefined) { navigator.mediaDevices = {}; }
  if (navigator.mediaDevices.getUserMedia === undefined) {
    navigator.mediaDevices.getUserMedia = function(constraints) {
      var getUserMedia = navigator.webkitGetUserMedia || navigator.mozGetUserMedia || navigator.msGetUserMedia;
      if (!getUserMedia) { return Promise.reject(new Error('getUserMedia is not implemented in this browser')); }
      return new Promise(function(resolve, reject) { getUserMedia.call(navigator, constraints, resolve, reject); });
    }
  }

  function detectCameras() {
    try {
      return navigator.mediaDevices.enumerateDevices()
        .then(function(devices){
          var vids = [];
          for (var i=0;i<devices.length;i++) { if (devices[i].kind === 'videoinput') vids.push(devices[i]); }
          frontDeviceId = null; backDeviceId = null;
          for (var j=0;j<vids.length;j++){
            var lbl = (vids[j].label || '').toLowerCase();
            if (lbl.indexOf('front') !== -1 || lbl.indexOf('user') !== -1) { frontDeviceId = vids[j].deviceId; }
            if (lbl.indexOf('back') !== -1 || lbl.indexOf('rear') !== -1 || lbl.indexOf('environment') !== -1) { backDeviceId = vids[j].deviceId; }
          }
          if (!frontDeviceId && vids.length) frontDeviceId = vids[0].deviceId;
          if (!backDeviceId && vids.length > 1) backDeviceId = vids[vids.length-1].deviceId;
          if (switchBtn) switchBtn.title = (frontDeviceId && backDeviceId) ? 'Switch Front/Back' : 'Switch Camera';
        }).catch(function(){});
    } catch(_) { return Promise.resolve(); }
  }

  function stopCamera() {
    if (signInterval) { clearInterval(signInterval); signInterval = null; }
    if (videoStream) {
      try { videoStream.getTracks().forEach(function(track){ track.stop(); }); } catch(e) {}
      videoStream = null;
    }
    videoEl.style.display = 'none';
    signBtn.classList.remove('active');
    if(switchBtn) switchBtn.style.display = 'none';
    try { fetch('/stop_camera', { method: 'POST' }); } catch(e) {}
  }

  function startCameraWithConstraints(constraints, onSuccess, onFailure) {
    try {
      navigator.mediaDevices.getUserMedia(constraints)
        .then(function(stream){ onSuccess(stream); })
        .catch(function(err){ onFailure(err); });
    } catch(e) { onFailure(e); }
  }

  window.toggleSign = function() {
    if (signInterval) { stopCamera(); }
    else {
      var constraints = { video: { width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 30 } } };
      if (currentDeviceId) {
        constraints.video.deviceId = { exact: currentDeviceId };
      } else {
        constraints.video.facingMode = currentFacingMode;
      }
      startCameraWithConstraints(constraints, function(stream){
        videoStream = stream;
        var track = videoStream.getVideoTracks()[0];
        var settings = track.getSettings ? track.getSettings() : {};
        if (settings.deviceId) currentDeviceId = settings.deviceId;
        if (settings.facingMode) currentFacingMode = settings.facingMode;
        videoEl.srcObject = videoStream;
        videoEl.style.display = 'block';
        signBtn.classList.add('active');
        if(switchBtn) switchBtn.style.display = 'block';
        var isUser = (currentFacingMode === 'user') || (track.label && track.label.toLowerCase().indexOf('front') !== -1);
        videoEl.style.transform = isUser ? 'scaleX(-1)' : 'scaleX(1)';
        videoEl.onloadedmetadata = function(){
          // Downscale capture canvas to reduce encode cost and flicker
          var vw = videoEl.videoWidth || 640;
          var vh = videoEl.videoHeight || 480;
          var targetW = 320; // capture width
          var targetH = Math.round(vh * (targetW / vw));
          if (!isFinite(targetH) || targetH < 1) targetH = 240;
          canvasEl.width = targetW;
          canvasEl.height = targetH;
          startSendingFrames();
        };
        detectCameras();
      }, function(err){
        var msg = (err && err.name) ? err.name : (err && err.message) ? err.message : 'Unknown error';
        if (!isSecure) {
          alert("Camera requires HTTPS. Use the Internet link (https) or allow insecure origins in Chrome flags. " + msg);
          return;
        }
        startCameraWithConstraints({ video: { facingMode: 'user' } }, function(stream){
          videoStream = stream;
          videoEl.srcObject = videoStream;
          videoEl.style.display = 'block';
          signBtn.classList.add('active');
          if(switchBtn) switchBtn.style.display = 'block';
          videoEl.onloadedmetadata = function(){
            canvasEl.width = videoEl.videoWidth;
            canvasEl.height = videoEl.videoHeight;
            startSendingFrames();
          };
          detectCameras();
        }, function(err2){
          var e1 = (err && (err.name || err.message)) ? (err.name || err.message) : '';
          var e2 = (err2 && (err2.name || err2.message)) ? (err2.name || err2.message) : '';
          alert("Camera not available. Tips:\\n\\n- Use the HTTPS Internet link.\\n- Allow camera permission.\\n- Try switching front/back.\\n\\nDetails: " + e1 + " " + e2);
        });
      });
    }
  };

  window.switchCamera = function() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return;
    try {
      if (videoStream) {
        try { videoStream.getTracks().forEach(function(t){ t.stop(); }); } catch(_) {}
        videoStream = null;
      }
      // Simple and robust: toggle facingMode between user and environment
      currentFacingMode = (currentFacingMode === 'user') ? 'environment' : 'user';
      currentDeviceId = null;
      var constraints = {
        video: {
          facingMode: { ideal: currentFacingMode },
          width: { ideal: 640 },
          height: { ideal: 480 }
        }
      };
      navigator.mediaDevices.getUserMedia(constraints)
        .then(function(stream){
          videoStream = stream;
          var track = videoStream.getVideoTracks()[0];
          var settings = track.getSettings ? track.getSettings() : {};
          if (settings.facingMode) currentFacingMode = settings.facingMode;
          if (settings.deviceId) currentDeviceId = settings.deviceId;
          videoEl.srcObject = videoStream;
          var isUser = (currentFacingMode === 'user') || (track.label && track.label.toLowerCase().indexOf('front') !== -1);
          videoEl.style.transform = isUser ? 'scaleX(-1)' : 'scaleX(1)';
          videoEl.style.display = 'block';
          if (switchBtn) switchBtn.style.display = 'block';
          detectCameras();
        })
        .catch(function(e){
          // Fallback to plain facingMode toggle without ideal hint
          currentFacingMode = (currentFacingMode === 'environment') ? 'user' : 'environment';
          currentDeviceId = null;
          navigator.mediaDevices.getUserMedia({ video: { facingMode: currentFacingMode } })
            .then(function(stream){
              videoStream = stream;
              videoEl.srcObject = stream;
              videoEl.style.display = 'block';
            })
            .catch(function(){ alert("Could not switch camera: " + e.message); });
        });
    } catch (e) {}
  };

  function startSendingFrames() {
    var intervalMs = 80;
    var inFlight = false;
    signInterval = setInterval(function(){
      if (!videoStream || !signInterval || inFlight) return;
      try {
        inFlight = true;
        var ctx = canvasEl.getContext('2d');
        ctx.drawImage(videoEl, 0, 0, canvasEl.width, canvasEl.height);
        if (canvasEl.toBlob) {
          canvasEl.toBlob(function(blob){
            try {
              var reader = new FileReader();
              reader.onloadend = function(){
                try {
                  var dataUrl = reader.result;
                  fetch('/upload_frame', {
                    method: 'POST',
                    body: JSON.stringify({ image: dataUrl }),
                    headers: { 'Content-Type': 'application/json' }
                  }).catch(function(){}).finally(function(){ inFlight = false; });
                } catch(_) { inFlight = false; }
              };
              reader.readAsDataURL(blob);
            } catch(_) { inFlight = false; }
          }, 'image/jpeg', 0.5);
        } else {
          var dataUrl = canvasEl.toDataURL('image/jpeg', 0.5);
          fetch('/upload_frame', {
            method: 'POST',
            body: JSON.stringify({ image: dataUrl }),
            headers: { 'Content-Type': 'application/json' }
          }).catch(function(){}).finally(function(){ inFlight = false; });
        }
      } catch(e) { inFlight = false; }
    }, intervalMs);
  }

  function initQuickPhrases() {
    try {
      var chips = document.querySelectorAll('.quick-phrases .chip');
      for (var i=0;i<chips.length;i++){
        chips[i].addEventListener('click', function() {
          var text = this.getAttribute('data-text') || this.textContent.replace(/^\\s+|\\s+$/g, '');
          if (navigator.vibrate) navigator.vibrate(20);
          inputEl.value = text;
          window.sendMessage();
        });
      }
    } catch(e) {}
  }

  window.toggleTheme = function() {
    var isLight = document.body.classList.toggle('light-theme');
    var btn = document.querySelector('.theme-toggle');
    if (btn) btn.textContent = isLight ? 'Light' : 'Dark';
  };

  window.stopCamera = function() {
    if (signInterval) { clearInterval(signInterval); signInterval = null; }
    try { if (videoStream) { var tr = videoStream.getTracks(); for (var i=0;i<tr.length;i++) tr[i].stop(); } } catch(_) {}
    videoStream = null;
    try { videoEl.srcObject = null; } catch(_) {}
    videoEl.style.display = 'none';
    signBtn.classList.remove('active');
    if (switchBtn) switchBtn.style.display = 'none';
    try { fetch('/stop_camera', { method: 'POST' }); } catch(_) {}
  };

  function ensureJoinOverlay() {
    try {
      if (document.getElementById('join-overlay')) return;
      var ov = document.createElement('div');
      ov.id = 'join-overlay';
      ov.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.8);display:flex;align-items:center;justify-content:center;z-index:99999;';
      var card = document.createElement('div');
      card.style.cssText = 'background:#1e1e1e;color:#fff;padding:20px;border-radius:12px;width:300px;text-align:center;border:1px solid #333;';
      var h = document.createElement('div');
      h.textContent = 'Join Session';
      h.style.cssText = 'font-size:18px;margin-bottom:8px;';
      var p = document.createElement('div');
      p.textContent = 'Tap to enable camera and mic.';
      p.style.cssText = 'font-size:12px;color:#ccc;margin-bottom:12px;';
      var btn = document.createElement('button');
      btn.textContent = 'Join';
      btn.style.cssText = 'background:#0078D4;color:#fff;border:none;border-radius:8px;padding:10px 16px;cursor:pointer;font-weight:bold;';
      btn.onclick = function(){
        requestAccess()
          .then(function(){ try { document.body.removeChild(ov); } catch(_){} })
          .catch(function(){ try { document.body.removeChild(ov); } catch(_){} });
      };
      card.appendChild(h); card.appendChild(p); card.appendChild(btn);
      ov.appendChild(card);
      document.body.appendChild(ov);
    } catch(_) {}
  }

  function requestAccess() {
    return new Promise(function(resolve){
      var gotVideo = false, gotAudio = false;
      function done(){ if (gotVideo && gotAudio) resolve(); }
      try {
        navigator.mediaDevices.getUserMedia({ video: true })
          .then(function(s){ try { s.getTracks().forEach(function(t){ t.stop(); }); } catch(_){} gotVideo=true; done(); })
          .catch(function(){ gotVideo=true; done(); });
      } catch(_){ gotVideo=true; }
      try {
        navigator.mediaDevices.getUserMedia({ audio: true })
          .then(function(s){ try { s.getTracks().forEach(function(t){ t.stop(); }); } catch(_){} gotAudio=true; done(); })
          .catch(function(){ gotAudio=true; done(); });
      } catch(_){ gotAudio=true; }
    }).then(function(){
      try { window.toggleSign(); } catch(_) {}
      try { if (recognition && !micBtn.classList.contains('listening')) recognition.start(); } catch(_) {}
    });
  }

  connectSSE();
  function afterLoad(){ initQuickPhrases(); detectCameras(); ensureJoinOverlay(); }
  if (document.readyState === 'complete' || document.readyState === 'interactive') setTimeout(afterLoad, 0);
  else window.addEventListener('DOMContentLoaded', afterLoad);
})(); 
        """
