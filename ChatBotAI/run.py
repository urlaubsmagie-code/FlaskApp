"""
Run script for ChatBotAI development server
Usage: python run.py
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables from ChatBotAI/.env
from pathlib import Path
from dotenv import load_dotenv
env_path = Path(__file__).resolve().parent / '.env'
load_dotenv(env_path)

from ChatBotAI.app import run_development_server

if __name__ == '__main__':
    run_development_server()
