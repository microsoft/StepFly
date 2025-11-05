#!/usr/bin/env python3
"""
StepFly Terminal Launcher
Simple launcher script for the terminal interface
"""

import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import and run the terminal UI
from ui.terminal_ui import main

if __name__ == "__main__":
    main()
