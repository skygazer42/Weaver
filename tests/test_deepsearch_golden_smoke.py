import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_benchmark_script_supports_required_cli_args(tmp_path):
    output = tmp_path / "benchmark_report.json"
    script = ROOT / "scripts" / "benchmark_deep_research.py"

    cmd = [
        sys.executable,
        str(script),
        "--max-cases",
        "2",
        "--mode",
        "auto",
        "--output",
        str(output),
    ]
    subprocess.run(cmd, cwd=str(ROOT), check=True)

    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["mode"] == "auto"
    assert data["max_cases"] == 2
    assert len(data["cases"]) == 2
    assert data["summary"]["total_cases"] == 2
