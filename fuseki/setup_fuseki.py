import os
import sys
import shutil
import subprocess
import time
import signal
import urllib.request
import urllib.parse
import json

# CONFIGURATION
# We use os.path.join for cross platform
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEMA_DIR = os.path.join(BASE_DIR, "schema", "pokemon")
DATA_NQ = os.path.join(SCHEMA_DIR, "poke-a.nt")
DATA_TTL = os.path.join(SCHEMA_DIR, "pokemon.ttl")
DB_DIR = os.path.join(BASE_DIR, "pokemon_db")
SERVER_PORT = 3030
DATASET_NAME = "/pokemon"

# Global variable to hold the server process
server_process = None

def find_executable(name):
    """Finds the tool (handling .bat extensions for Windows)"""
    exe = shutil.which(name)
    if exe:
        return exe
    # Fallback check specifically for Windows users
    if os.name == 'nt':
        exe = shutil.which(name + ".bat")
        if exe: return exe
    return None

def cleanup(signum=None, frame=None):
    """Kills the server when the script exits"""
    global server_process
    print("\nStopping Fuseki Server...")

    if server_process:
        # On Windows, more aggressive to kill the subprocess tree
        if os.name == 'nt':
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(server_process.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            server_process.terminate()
            try:
                server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_process.kill()

    print("Goodbye!")
    sys.exit(0)

def main():
    global server_process

    print("--- Pokemon Knowledge Graph Setup ---")

    # Check Prerequisites
    if os.name == "nt":
        loader_cmd = find_executable("tdb2_tdbloader")  # windows naming
    else:
        loader_cmd = find_executable("tdb2.tdbloader")  # unix naming
    server_cmd = find_executable("fuseki-server")

    if not loader_cmd:
        expected = "tdb2_tdbloader (Windows)" if os.name == "nt" else "tdb2.tdbloader (Linux/macOS)"
        print(f"Error: '{expected}' not found. Is Apache Jena installed and in PATH?")
        sys.exit(1)
    if not server_cmd:
        print("Error: 'fuseki-server' not found. Is Fuseki installed and in PATH?")
        sys.exit(1)

    # Load Data (Idempotent)
    # Check if DB exists AND is not empty (Docker might create an empty mount point)
    db_exists = os.path.exists(DB_DIR) and os.listdir(DB_DIR)

    if db_exists:
        print(f"Database folder '{os.path.basename(DB_DIR)}' exists and is not empty. Skipping load.")
    else:
        print("Database not found or empty. Loading data...")
        if not os.path.exists(DATA_NQ) or not os.path.exists(DATA_TTL):
            print(f"Error: Data files not found in: {SCHEMA_DIR}")
            sys.exit(1)

        print(f"Loading data from {SCHEMA_DIR}...")
        try:
            # We run the loader command. Check=True throws error if it fails
            subprocess.run([loader_cmd, f"--loc={DB_DIR}", DATA_TTL, DATA_NQ], check=True)
            print("Data loaded successfully!")
        except subprocess.CalledProcessError:
            print("Error loading data.")
            sys.exit(1)

    # Register Signal Handlers (Ctrl+C)
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    # Start Server
    print(f"Starting Fuseki Server on port {SERVER_PORT}...")
    try:
        # Start Fuseki in the background
        popen_kwargs = {}
        if os.name == "nt":
            fuseki_home = os.environ.get("FUSEKI_HOME")
            if not fuseki_home or not os.path.isdir(fuseki_home):
                print("Error: FUSEKI_HOME is not set (or points to a missing folder).")
                print("Set FUSEKI_HOME to the Fuseki folder that contains fuseki-server.bat and fuseki-server.jar.")
                sys.exit(1)
            popen_kwargs["cwd"] = fuseki_home

        os.makedirs(DB_DIR, exist_ok=True)

        server_process = subprocess.Popen(
            [server_cmd, f"--loc={DB_DIR}", f"--port={SERVER_PORT}", DATASET_NAME],
            stdout=subprocess.DEVNULL, # Hide server logs to keep output clean (optional)
            stderr=subprocess.PIPE,     # Capture errors if it fails immediately
            **popen_kwargs
        )
        time.sleep(3) # Give it a moment to initialize

        # Check if it died immediately (e.g., port in use)
        if server_process.poll() is not None:
            _, stderr = server_process.communicate()
            print("Server failed to start. Error logs:")
            print(stderr.decode())
            sys.exit(1)

    except Exception as e:
        print(f"Failed to launch server: {e}")
        sys.exit(1)

    # Verify & Keep Alive
    print("Verifying SPARQL Endpoint...")
    query = "SELECT (COUNT(*) as ?count) WHERE { ?s ?p ?o }"
    params = urllib.parse.urlencode({'query': query, 'output': 'json'})
    url = f"http://localhost:{SERVER_PORT}{DATASET_NAME}/query?{params}"

    try:
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode())
            count = data["results"]["bindings"][0]["count"]["value"]

            print(f"VERIFICATION PASSED: Found {count} triples.")
            print("-" * 50)
            print(f"Endpoint: http://localhost:{SERVER_PORT}{DATASET_NAME}")
            print("-" * 50)
            print("Press Ctrl+C to stop.")

            # Keep Python running until Ctrl+C
            while True:
                time.sleep(1)

    except Exception as e:
        print("VERIFICATION FAILED.")
        print(f"Error: {e}")
        cleanup()

if __name__ == "__main__":
    main()
