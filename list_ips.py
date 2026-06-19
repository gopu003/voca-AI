
import socket

def list_ips():
    print(f"Hostname: {socket.gethostname()}")
    print(f"Default IP (gethostbyname): {socket.gethostbyname(socket.gethostname())}")

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        connected_ip = s.getsockname()[0]
        s.close()
        print(f"Socket connect method (8.8.8.8): {connected_ip}")
    except Exception as e:
        print(f"Socket connect method failed: {e}")

if __name__ == "__main__":
    list_ips()
