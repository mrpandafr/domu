#!/usr/bin/env python3
"""Start the Domu memory server. Works from any directory."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from domu.server import main

main()
