import socket
import subprocess
import sys
import os
import webbrowser
from threading import Timer

def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]

def open_browser(port):
    webbrowser.open_new(f'http://127.0.0.1:{port}')

if __name__ == '__main__':
    port = find_free_port()
    print(f"[System] Starting YouTube Whisperer on dynamic port {port}...")
    
    # Auto-open browser after a short delay
    Timer(1.5, open_browser, args=[port]).start()
    
    # Launch Streamlit with the dynamic port
    subprocess.run([
        sys.executable, "-m", "streamlit", "run", "app.py", 
        f"--server.port={port}", 
        "--server.headless=true",
        "--server.maxUploadSize=2000"
    ])
