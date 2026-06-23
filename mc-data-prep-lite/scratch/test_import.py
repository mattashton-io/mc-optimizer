import sys

sys.modules['OpenSSL'] = None

import traceback

print("Testing imports with OpenSSL blocked...")
try:
    print("Base Google libraries imported successfully.")

    print("ADK imported successfully.")

    # Try importing our app modules
    print("app.agent imported successfully.")

    print("app.data_prep imported successfully.")

    print("All imports completed successfully!")
except Exception:
    print("\n--- TRACEBACK ---")
    traceback.print_exc()
    print("-----------------\n")
