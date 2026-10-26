import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("report", ROOT / "tools/report.py")
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def test_diag_runs_and_summary(tmp_path):
    lines = [{"event": "start", "uptime_s": 0, "mem_peak_mb": 3, "fps_processed": 0}]
    for i in range(1, 190):
        lines.append({"event": "tick", "uptime_s": i * 10, "fps_processed": 60.0,
                      "mem_peak_mb": 8.0, "frames_received": i * 600, "frames_dropped": 1,
                      "buffer_w": 884, "buffer_h": 1920, "pixel_format": "420f",
                      "tiles_rgb": [[251, 217, 163]] * 15 + [[252, 252, 252]]})  # fmt: skip
    lines.append({"event": "finish", "uptime_s": 1900, "mem_peak_mb": 8.0})
    path = tmp_path / "diag.jsonl"
    path.write_text("\n".join(json.dumps(x) for x in lines))
    runs = report.diag_runs(path)
    assert len(runs) == 1
    s = report.summarise_run(runs[0])
    assert s["duration_min"] == 31.7 and s["finished_cleanly"]
    assert s["mem_peak_mb"] == 8.0 and s["fps_p50"] == 60.0
    assert s["resting_rgb_phone"] == [251.0, 217.0, 163.0]
    assert s["buffer"] == "884x1920 420f"
