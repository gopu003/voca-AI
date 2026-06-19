import urllib.request
import json
import base64
import cv2
import numpy as np

try:
    # Create a dummy green image
    img = np.zeros((240, 320, 3), dtype=np.uint8)
    cv2.rectangle(img, (50, 50), (100, 100), (0, 255, 0), -1)
    
    # Encode to JPEG
    _, buffer = cv2.imencode('.jpg', img)
    img_str = base64.b64encode(buffer).decode('utf-8')
    
    # Prepare payload
    payload = {'image': img_str}
    data = json.dumps(payload).encode('utf-8')
    
    # Send POST request
    req = urllib.request.Request(
        'http://localhost:8000/upload_frame', 
        data=data, 
        headers={'Content-Type': 'application/json'}
    )
    
    with urllib.request.urlopen(req) as response:
        print(f"Response Code: {response.getcode()}")
        print(f"Response Body: {response.read().decode('utf-8')}")
        
except Exception as e:
    print(f"Test Failed: {e}")
