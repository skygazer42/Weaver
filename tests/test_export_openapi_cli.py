import json
import subprocess
import sys


def test_export_openapi_cli_writes_json_to_stdout():
    proc = subprocess.run(
        [sys.executable, "scripts/export_openapi.py"],
        check=True,
        capture_output=True,
        text=True,
    )
    spec = json.loads(proc.stdout)
    assert "openapi" in spec

