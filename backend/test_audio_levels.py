#!/usr/bin/env python3
"""
Test audio level publishing to Redis
"""
import redis
import json
import time
import random
import math

def main():
    r = redis.Redis(host='localhost', port=6379, decode_responses=True)
    
    print("Publishing fake audio levels to Redis...")
    print("Check the frontend audio meter - it should start moving!")
    
    t = 0
    while True:
        # Generate a sine wave pattern for visual effect
        level = abs(math.sin(t)) * 0.3 + random.random() * 0.2
        peak = level + random.random() * 0.1
        
        message = {
            'timestamp': time.time(),
            'audio_level': level,
            'level': level,  # Both formats for compatibility
            'peak_level': peak,
            'status': 'active'
        }
        
        # Publish to the audio:levels channel
        r.publish('audio:levels', json.dumps(message))
        
        print(f"Published level: {level:.3f}")
        
        t += 0.1
        time.sleep(0.1)  # 10 updates per second

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped publishing audio levels")
