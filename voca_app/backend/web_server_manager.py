import threading
import time
import queue
from .web_server import VocaWebServer

class WebServerManager:
    def __init__(self, status_callback):
        self.server = None
        self.thread = None
        self.status_callback = status_callback
        self.running = False
        self.preferred_hostname = None

    def start(self, use_ngrok):
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._run, args=(use_ngrok,), daemon=True)
        self.thread.start()

    def _run(self, use_ngrok):
        try:
            self.server = VocaWebServer()
            try:
                # Inject preferred hostname if provided
                if self.preferred_hostname and hasattr(self.server, 'set_preferred_hostname'):
                    self.server.set_preferred_hostname(self.preferred_hostname)
            except Exception:
                pass
            url = self.server.start(use_ngrok=use_ngrok)
            if url:
                self.status_callback("RUNNING", {
                    "url": url,
                    "local_url": self.server.local_url,
                    "public_url": self.server.public_url,
                    "ngrok_error": getattr(self.server, "ngrok_error", None),
                    "cfd_error": getattr(self.server, "cfd_error", None),
                    "cfd_url": getattr(self.server, "cfd_url", None)
                })
            else:
                self.status_callback("ERROR", {"message": "Server failed to start."})
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.status_callback("ERROR", {"message": str(e)})
        
        # Keep thread alive while server is running
        while self.running and self.server and self.server.running:
            time.sleep(1)

    def stop(self):
        self.running = False
        if self.server:
            self.server.stop()
        if self.thread:
            self.thread.join(timeout=2)
        self.status_callback("STOPPED", {})

    def get_server_instance(self):
        return self.server
