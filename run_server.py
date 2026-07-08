#!/usr/bin/env python3
"""Lance le serveur Domu. Lancer depuis n'importe où."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from domu.server import main

main()
