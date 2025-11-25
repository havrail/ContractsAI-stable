import subprocess
import time
import os
import sys
import threading

def run_backend():
    print("Starting Backend (Production Mode - No Auto-Reload)...")
    # Get the script's directory and go to src_python
    script_dir = os.path.dirname(os.path.abspath(__file__))
    src_python_dir = os.path.join(script_dir, "src_python")
    os.chdir(src_python_dir)
    # Run uvicorn WITHOUT --reload for stable production-like mode
    subprocess.run([sys.executable, "-m", "uvicorn", "api:app", "--port", "8000", "--host", "127.0.0.1"])

def run_frontend():
    print("Starting Frontend...")
    # Get script directory and go to contracts-ai-ui
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ui_dir = os.path.join(script_dir, "contracts-ai-ui")
    os.chdir(ui_dir)
    # Use npm run dev for web UI (faster/safer than tauri dev for quick check)
    subprocess.run(["npm", "run", "dev"], shell=True)

if __name__ == "__main__":
    # Start backend in a separate thread
    t_backend = threading.Thread(target=run_backend)
    t_backend.daemon = True
    t_backend.start()

    time.sleep(3) # Wait for backend to init

    # Run frontend in main thread
    run_frontend()
