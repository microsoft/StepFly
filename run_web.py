#!/usr/bin/env python3
"""
StepFly Web Dashboard Launcher
Simple launcher script for the web interface with auto browser opening
"""

import sys
import os
import webbrowser
import time
import threading

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import and run the web UI
from ui.web_ui_run import main

def open_browser(delay=2):
    """Open browser after a short delay to allow server to start"""
    time.sleep(delay)
    webbrowser.open("http://localhost:8080")

if __name__ == "__main__":
    # Start browser opening in background thread
    browser_thread = threading.Thread(target=open_browser)
    browser_thread.daemon = True
    browser_thread.start()
    
    print("🌐 Web dashboard will open at: http://localhost:8080")
    
    # Run the web server
    main()
