
import socket

def get_ips():
    available_ips = []
    primary_ip = None
    
    try:
        # 1. Try connecting to internet
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        primary_ip = s.getsockname()[0]
        s.close()
        print(f"Primary IP: {primary_ip}")
    except Exception as e:
        print(f"Primary IP failed: {e}")

    try:
        # 2. Get all interface IPs
        hostname = socket.gethostname()
        all_ips = socket.gethostbyname_ex(hostname)[2]
        print(f"All IPs: {all_ips}")
        
        # Filter IPs
        filtered_ips = []
        for ip in all_ips:
            if ip.startswith("127."): continue
            if ip.startswith("169.254."): continue # APIPA
            filtered_ips.append(ip)
        
        # Sort remaining IPs
        filtered_ips.sort(key=lambda x: 0 if x.startswith("192.168.") else (1 if x.startswith("10.") else 2))
        
        # Construct final list
        if primary_ip:
            available_ips.append(primary_ip)
            # Add others that are not primary
            for ip in filtered_ips:
                if ip != primary_ip and ip not in available_ips:
                    available_ips.append(ip)
        else:
            available_ips = filtered_ips
            
    except Exception as e:
        print(f"All IPs failed: {e}")
    
    # Fallback
    if not available_ips:
        available_ips.append("127.0.0.1")

    print(f"Final Available IPs: {available_ips}")

get_ips()
