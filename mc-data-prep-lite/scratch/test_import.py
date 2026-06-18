import sys
sys.modules['OpenSSL'] = None

import traceback

print("Testing imports with OpenSSL blocked...")
try:
    import google.auth
    import google.genai
    print("Base Google libraries imported successfully.")
    
    from google.adk.agents import Agent
    from google.adk.apps import App
    print("ADK imported successfully.")
    
    # Try importing our app modules
    import app.agent
    print("app.agent imported successfully.")
    
    import app.data_prep
    print("app.data_prep imported successfully.")
    
    print("All imports completed successfully!")
except Exception as e:
    print("\n--- TRACEBACK ---")
    traceback.print_exc()
    print("-----------------\n")
