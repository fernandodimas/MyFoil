#!/usr/bin/env python3
"""
Test script to verify server responsiveness during file identification
"""
import requests
import time
import threading
import sys

BASE_URL = "http://localhost:8465"
session = requests.Session()

def login():
    """Login to get session"""
    resp = session.post(f"{BASE_URL}/login", data={
        'user': 'admin',
        'password': 'password',
        'remember': False
    }, allow_redirects=False)
    print(f"Login status: {resp.status_code}")
    return resp.status_code in [200, 302]

def check_responsiveness():
    """Continuously check if server responds to requests"""
    start_time = time.time()
    check_count = 0
    slow_responses = 0
    
    while time.time() - start_time < 60:  # Run for 60 seconds
        try:
            req_start = time.time()
            resp = session.get(f"{BASE_URL}/api/stats/overview", timeout=5)
            req_time = time.time() - req_start
            
            check_count += 1
            if req_time > 2:
                slow_responses += 1
                print(f"⚠️  Slow response: {req_time:.2f}s (check #{check_count})")
            else:
                print(f"✓ Response time: {req_time:.3f}s (check #{check_count})")
            
            time.sleep(2)  # Check every 2 seconds
        except requests.exceptions.Timeout:
            print(f"❌ TIMEOUT on check #{check_count}")
            slow_responses += 1
        except Exception as e:
            print(f"❌ Error: {e}")
            break
    
    print(f"\n=== Responsiveness Test Results ===")
    print(f"Total checks: {check_count}")
    print(f"Slow/timeout responses: {slow_responses}")
    print(f"Success rate: {((check_count - slow_responses) / check_count * 100):.1f}%")

def main():
    print("=== MyFoil Server Responsiveness Test ===\n")
    
    if not login():
        print("❌ Failed to login. Check credentials.")
        return 1
    
    print("✓ Logged in successfully\n")
    print("Starting responsiveness checks...")
    print("(This will run for 60 seconds)\n")
    
    check_responsiveness()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
