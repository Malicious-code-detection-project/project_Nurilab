"""
Sample algorithm script with intentional security red flags for testing.
This script implements a basic sorting/searching logic but includes
suspicious calls and hard-coded secrets for the static analyzer to find.
"""

import os
import pickle
import requests
import subprocess
from datetime import datetime

# Red Flag 1: Hard-coded sensitive information
API_KEY = "ak-test-7729-x921-vllm-sglang-key"
DB_CONNECTION = "postgresql://admin:super_secret_password_123@localhost:5432/mydb"

def bubble_sort(arr):
    """A standard bubble sort algorithm (~100 lines total for the file)."""
    n = len(arr)
    for i in range(n):
        for j in range(0, n-i-1):
            if arr[j] > arr[j+1]:
                arr[j], arr[j+1] = arr[j+1], arr[j]
    return arr

def analyze_and_report(data):
    """Process data and perform suspicious actions."""
    
    print(f"[{datetime.now()}] Starting data analysis...")
    
    # Red Flag 2: Dynamic execution
    # Using eval to apply a 'filter' from a string
    user_filter = "x > 0"
    filtered_data = [x for x in data if eval(user_filter.replace('x', str(x)))]
    
    # Red Flag 3: Command execution
    # Running a shell command with user-controlled-like input
    report_name = "report_2026.txt"
    os.system(f"echo 'Analysis Result: {len(filtered_data)} items' > {report_name}")
    
    # Red Flag 4: Network access
    # Sending stats to a remote server
    try:
        requests.post("https://api.example-security.com/v1/metrics", 
                      json={"count": len(filtered_data)},
                      headers={"X-API-KEY": API_KEY})
    except Exception:
        pass

    # Red Flag 5: Unsafe Deserialization
    # Loading a cache file using pickle
    cache_file = "analysis_cache.pkl"
    if os.path.exists(cache_file):
        with open(cache_file, "rb") as f:
            # Dangerous: pickle.load can execute arbitrary code
            cached_result = pickle.load(f)
            print(f"Loaded cache: {cached_result}")

    return filtered_data

def main():
    # Sample data for sorting
    raw_data = [64, 34, 25, 12, 22, 11, 90, -5, 0, 15, 33, 42, 100, 5, 8]
    
    # Run algorithm
    sorted_data = bubble_sort(raw_data)
    print(f"Sorted data: {sorted_data}")
    
    # Run suspicious analysis
    results = analyze_and_report(sorted_data)
    
    # Red Flag 6: Subprocess with shell=True
    subprocess.run("dir", shell=True)
    
    print(f"Analysis complete. Found {len(results)} matches.")

if __name__ == "__main__":
    main()
