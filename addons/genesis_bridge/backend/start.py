"""
Genesis Engine backend launcher.
Run this script with the venv Python to start the server from any working directory.
"""
import sys
import os
import atexit

# Ensure all backend modules resolve correctly regardless of CWD
_backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _backend_dir)
os.chdir(_backend_dir)

# Write PID file so the Godot plugin can kill this process directly,
# independent of whichever terminal emulator was used to launch us.
_pid_file = os.path.join(_backend_dir, ".pid")
with open(_pid_file, "w") as _f:
    _f.write(str(os.getpid()))

@atexit.register
def _cleanup_pid():
    try:
        os.remove(_pid_file)
    except OSError:
        pass

import uvicorn

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    uvicorn.run("main:app", host="127.0.0.1", port=port, log_level="info")
