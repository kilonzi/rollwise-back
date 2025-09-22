import sys
import os

# Ensure project root is on sys.path so tests can import the `app` package
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Optional: set test-related environment variables
os.environ.setdefault("ENV", "test")
