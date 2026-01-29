import sys
import threading
import time
from pathlib import Path

import requests

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from http.server import HTTPServer

from tools.gt_relabel_gui.server import Handler


def run_server(server):
    server.serve_forever()


def test_server_serves_updated_js():
    # Setup server
    port = 8999
    host = "127.0.0.1"

    # Mock config for GT mode
    config_path = Path("tests/mock_gt_config.json")
    config_path.write_text('{"pages": []}')

    # We need to set the server root and config manually as we are bypassing main()
    server = HTTPServer((host, port), Handler)
    server.ui_root = Path("tools/gt_relabel_gui").resolve()
    server.mode = "gt"
    server.root = Path(".").resolve()
    server.gt_config = []

    thread = threading.Thread(target=run_server, args=(server,))
    thread.daemon = True
    thread.start()

    time.sleep(1)  # Wait for startup

    try:
        # Check if app_gt.js is served and contains new logic
        resp = requests.get(f"http://{host}:{port}/app_gt.js")
        assert resp.status_code == 200
        content = resp.text

        # Verify key features exist in the code
        assert "selectedIndices = new Set()" in content, "Multi-select Set not found"
        assert 'e.key.toLowerCase() === "d"' in content, "Draw shortcut (d) not found"
        assert 'e.key.toLowerCase() === "s"' in content, "Select shortcut (s) not found"
        assert "editableBoxes.splice(idx, 1)" in content, "Delete splice logic not found"

        print("SUCCESS: app_gt.js served and contains new feature logic.")
    except Exception as e:
        print(f"FAILURE: {e}")
        sys.exit(1)
    finally:
        server.shutdown()
        if config_path.exists():
            config_path.unlink()


if __name__ == "__main__":
    test_server_serves_updated_js()
