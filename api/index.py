import os
import sys

# Add project root to sys.path for backend imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from backend.main import app
    handler = app
except Exception as e:
    import sys
    import traceback
    sys.stderr.write("CRITICAL: Failed to import backend.main:\n")
    traceback.print_exc(file=sys.stderr)
    raise e
