"""
Smoke test that records the website API's current behavior (status codes + response bodies).

Phase 1 of the spoke refactor moves the controller logic out of website.py. This test is the
pass/fail check for that move: record a baseline before the refactor, then compare after it.

Usage (from the launch_controller folder):
    python tests/smoke_test_website.py --record   # write tests/baseline/website_api.json
    python tests/smoke_test_website.py            # run again and diff against the baseline

Notes:
- Runs in MOCK_MODE against config/demo. Log paths are redirected to a temp folder in memory;
  the config files are not modified.
- Flask's built-in server is never started; requests go through Flask's test client.
- Mock sensor pressures are pinned to fixed values so safe-state selection is deterministic.
- Takes ~25 s because it waits through real step / safe-state actions (2 s and 5 s waits in config).
"""
import argparse
import copy
import difflib
import json
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Settings must be patched before importing modules that read them at import time (valve.py, pressure_sensor.py).
import src.settings as settings
settings.MOCK_MODE = True
settings.PRINT_VALVE_STATES = False
settings.PRINT_PRESSURE_SENSOR_READINGS = False
settings.PRINT_CONTROLLER_STATUS = False
settings.PRINT_CONTROLLER_ERRORS = False
settings.PRINT_WEBSITE_STATUS = False
settings.PRINT_WEBSITE_ERRORS = False

import flask
from src.controller import Controller
from src.pressure_sensor import PressureSensor
from src.operations import ControllerOperations
from src.website import ControllerWebsite

BASELINE_PATH = os.path.join(ROOT, "tests", "baseline", "website_api.json")
CONFIG_DIR = os.path.join(ROOT, "config", "demo")

# Never start the real web server (it would bind port 8080).
flask.Flask.run = lambda *args, **kwargs: None

# Pin mock pressures: sensor id -> pressure. Change via set_pressures().
_PINNED_PRESSURES = {}
PressureSensor.pressure = property(lambda self: _PINNED_PRESSURES.get(self.id, 0.0))

# Fields whose values depend on wall-clock timing; replaced with a placeholder before comparing.
_TIMING_FIELDS = {"pulse_elapsed", "pulse_remaining"}


def build_website(controller: Controller, config: dict):
    """Builds the website the same way main.py does. Returns (operations, website)."""
    operations = ControllerOperations.from_config(controller, config)
    return operations, ControllerWebsite.from_config(operations, config)


def set_pressures(controller: Controller, pressures: dict) -> None:
    """Pins sensor pressures and waits until the controller's read thread has picked them up."""
    _PINNED_PRESSURES.clear()
    _PINNED_PRESSURES.update(pressures)
    wait_until(lambda: all(
        s["current_pressure"] == pressures.get(s["id"], 0.0) for s in controller.pressure_sensor_info
    ), "pinned pressures applied")


def wait_until(condition, description: str, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return
        time.sleep(0.05)
    raise TimeoutError(f"Timed out waiting for: {description}")


def normalize(value):
    """Replaces timing-dependent values so runs can be compared."""
    if isinstance(value, dict):
        return {k: ("<float>" if k in _TIMING_FIELDS else normalize(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize(v) for v in value]
    return value


def load_config(name: str, log_dir: str, overrides: dict = None) -> dict:
    with open(os.path.join(CONFIG_DIR, name)) as f:
        config = json.load(f)
    general = config["general_config"]
    for key in list(general):
        if key.endswith("_log_path"):
            general[key] = os.path.join(log_dir, f"{key}.txt")
    general.update(overrides or {})
    return config


class Recorder:
    """Sends requests through the Flask test client and records normalized results."""

    def __init__(self, website: ControllerWebsite, prefix: str = ""):
        self.client = website._app.test_client()
        self.prefix = prefix
        self.results = []

    def call(self, name: str, method: str, path: str, body=None, raw_body: str = None):
        kwargs = {}
        if raw_body is not None:
            kwargs["data"] = raw_body
            kwargs["content_type"] = "text/plain"
        elif body is not None:
            kwargs["json"] = body
        response = self.client.open(path, method=method, **kwargs)
        data = response.get_json(silent=True)
        entry = {
            "name": self.prefix + name,
            "request": f"{method} {path}",
            "body": body if raw_body is None else f"<raw> {raw_body}",
            "status": response.status_code,
            "response": normalize(data) if data is not None else f"<{response.mimetype}>",
        }
        self.results.append(entry)
        return response.status_code, data

    def get(self, name, path):
        return self.call(name, "GET", path)

    def post(self, name, path, body=None, raw_body=None):
        return self.call(name, "POST", path, body=body, raw_body=raw_body)

    def snapshot(self, name):
        """Records current valve state, safing state and procedure status."""
        self.get(f"{name}: valves", "/api/get_valve_info")
        self.get(f"{name}: safing", "/api/is_safing")
        self.get(f"{name}: procedure status", "/api/get_procedure_status")


def is_idle(rec: Recorder) -> bool:
    status = rec.client.get("/api/get_procedure_status").get_json()
    safing = rec.client.get("/api/is_safing").get_json()
    return status["executing"] is None and not safing["safing"]


def valve_state(rec: Recorder, valve_id: int) -> str:
    return next(v["current_state"] for v in rec.client.get("/api/get_valve_info").get_json() if v["id"] == valve_id)


def no_valves_pulsing(rec: Recorder) -> bool:
    return not any(v["is_pulsing"] for v in rec.client.get("/api/get_valve_info").get_json())


def run_main_scenarios(log_dir: str) -> list:
    controller = Controller.from_config(load_config("controller_config.json", log_dir))
    operations, website = build_website(controller, load_config("website_config.json", log_dir))
    rec = Recorder(website)
    set_pressures(controller, {1: 25.0, 2: 50.0})

    # --- Read-only endpoints ---
    rec.get("index page", "/")
    rec.get("server status", "/api/get_server_status")
    rec.get("heartbeat", "/api/send_heartbeat")
    rec.get("valve info", "/api/get_valve_info")
    rec.get("sensor info", "/api/get_sensor_info")
    rec.get("procedures", "/api/get_procedures")
    rec.get("invalid valve states", "/api/get_invalid_valve_states")
    rec.get("website title", "/api/get_website_title")
    rec.get("safe mode", "/api/get_safe_mode")
    rec.get("procedure status", "/api/get_procedure_status")
    rec.get("is safing", "/api/is_safing")

    # --- set_valve_states ---
    rec.post("set valve 1 open", "/api/set_valve_states", {"1": "open"})
    rec.get("after set valve 1 open", "/api/get_valve_info")
    rec.post("set valve 1 closed (case + whitespace)", "/api/set_valve_states", {"1": "  CLOSED "})
    rec.post("set two valves", "/api/set_valve_states", {"1": "open", "2": "open"})
    rec.post("empty dict", "/api/set_valve_states", {})
    rec.post("unknown valve id", "/api/set_valve_states", {"99": "open"})
    rec.post("non-integer valve id", "/api/set_valve_states", {"abc": "open"})
    rec.post("non-string action", "/api/set_valve_states", {"1": 5})
    rec.post("invalid action", "/api/set_valve_states", {"1": "sideways"})
    rec.post("invalid pulse duration", "/api/set_valve_states", {"1": "pulse:abc"})
    rec.post("negative pulse duration", "/api/set_valve_states", {"1": "pulse:-1"})
    rec.post("partial failure", "/api/set_valve_states", {"1": "closed", "99": "open"})
    rec.get("after partial failure (valve 1 closed)", "/api/get_valve_info")
    rec.post("body is a list", "/api/set_valve_states", ["1", "open"])
    rec.post("body not JSON", "/api/set_valve_states", raw_body="1=open")
    rec.post("reset valves closed", "/api/set_valve_states", {"1": "closed", "2": "closed"})

    # --- Pulse ---
    rec.post("pulse valve 2", "/api/set_valve_states", {"2": "pulse:0.5"})
    rec.get("during pulse", "/api/get_valve_info")
    rec.post("modify valve while pulsing", "/api/set_valve_states", {"2": "open"})
    wait_until(lambda: no_valves_pulsing(rec), "pulse to finish")
    rec.get("after pulse", "/api/get_valve_info")

    # --- Safe mode ---
    rec.post("safe mode: no JSON body", "/api/set_safe_mode", raw_body="true")
    rec.post("safe mode: missing field", "/api/set_safe_mode", {})
    rec.post("safe mode: non-bool", "/api/set_safe_mode", {"safe_mode": "yes"})
    rec.post("safe mode: enable", "/api/set_safe_mode", {"safe_mode": True})
    rec.get("safe mode: after enable", "/api/get_safe_mode")
    rec.post("safe mode: disable", "/api/set_safe_mode", {"safe_mode": False})
    rec.get("safe mode: after disable", "/api/get_safe_mode")

    # --- start_step_execution validation ---
    rec.post("start step: no JSON body", "/api/start_step_execution", raw_body="x")
    rec.post("start step: missing procedure_index", "/api/start_step_execution", {"step_index": 0})
    rec.post("start step: non-int procedure_index", "/api/start_step_execution", {"procedure_index": "a", "step_index": 0})
    rec.post("start step: missing step_index", "/api/start_step_execution", {"procedure_index": 0})
    rec.post("start step: non-int step_index", "/api/start_step_execution", {"procedure_index": 0, "step_index": "a"})
    rec.post("start step: procedure out of range", "/api/start_step_execution", {"procedure_index": 9, "step_index": 0})
    rec.post("start step: step out of range", "/api/start_step_execution", {"procedure_index": 0, "step_index": 9})

    # --- Step execution and what is blocked during it ---
    # Procedure 0 step 0: open valve 1, wait 2 s, open valve 2.
    rec.post("start step 0/0", "/api/start_step_execution", {"procedure_index": 0, "step_index": 0})
    wait_until(lambda: valve_state(rec, 1) == "open", "step 0/0 first action")
    rec.snapshot("during step 0/0")
    rec.post("during step: set valve", "/api/set_valve_states", {"2": "open"})
    rec.post("during step: start another step", "/api/start_step_execution", {"procedure_index": 0, "step_index": 2})
    rec.post("during step: safe system", "/api/safe_system")
    rec.post("during step: reset same procedure", "/api/reset_procedure", {"procedure_index": 0})
    rec.post("during step: reset other procedure", "/api/reset_procedure", {"procedure_index": 1})
    rec.post("during step: set completion", "/api/set_step_completion", {"procedure_index": 0, "step_index": 1, "completed": True})
    wait_until(lambda: is_idle(rec), "step 0/0 to finish")
    rec.snapshot("after step 0/0")

    # Procedure 0 step 2: grouped pulse step (pulse valve 2 for 0.5 s).
    rec.post("start pulse step 0/2", "/api/start_step_execution", {"procedure_index": 0, "step_index": 2})
    wait_until(lambda: is_idle(rec) and no_valves_pulsing(rec), "step 0/2 to finish")
    rec.snapshot("after step 0/2")

    # --- set_step_completion ---
    rec.post("completion: no JSON body", "/api/set_step_completion", raw_body="x")
    rec.post("completion: missing procedure_index", "/api/set_step_completion", {"step_index": 0, "completed": True})
    rec.post("completion: non-int procedure_index", "/api/set_step_completion", {"procedure_index": "a", "step_index": 0, "completed": True})
    rec.post("completion: missing step_index", "/api/set_step_completion", {"procedure_index": 0, "completed": True})
    rec.post("completion: non-int step_index", "/api/set_step_completion", {"procedure_index": 0, "step_index": "a", "completed": True})
    rec.post("completion: missing completed", "/api/set_step_completion", {"procedure_index": 0, "step_index": 0})
    rec.post("completion: non-bool completed", "/api/set_step_completion", {"procedure_index": 0, "step_index": 0, "completed": 1})
    rec.post("completion: procedure out of range", "/api/set_step_completion", {"procedure_index": 9, "step_index": 0, "completed": True})
    rec.post("completion: step out of range", "/api/set_step_completion", {"procedure_index": 0, "step_index": 9, "completed": True})
    rec.post("completion: mark 1/1 complete", "/api/set_step_completion", {"procedure_index": 1, "step_index": 1, "completed": True})
    rec.post("completion: mark 0/0 incomplete", "/api/set_step_completion", {"procedure_index": 0, "step_index": 0, "completed": False})
    rec.get("completion: status", "/api/get_procedure_status")

    # --- reset_procedure ---
    rec.post("reset: no JSON body", "/api/reset_procedure", raw_body="x")
    rec.post("reset: missing procedure_index", "/api/reset_procedure", {})
    rec.post("reset: non-int procedure_index", "/api/reset_procedure", {"procedure_index": "a"})
    rec.post("reset: out of range", "/api/reset_procedure", {"procedure_index": 9})
    rec.post("reset: procedure 0", "/api/reset_procedure", {"procedure_index": 0})
    rec.get("reset: status", "/api/get_procedure_status")

    # --- safe_system: "Safe state 1" (pressure 1 < 50 and valve 1 closed; opens 1, waits 2 s, opens 2) ---
    rec.post("safe system 1: close valves", "/api/set_valve_states", {"1": "closed", "2": "closed"})
    rec.post("safe system 1: start", "/api/safe_system")
    wait_until(lambda: valve_state(rec, 1) == "open", "safe system 1 first action")
    rec.snapshot("during safe system 1")
    rec.post("during safing: set valve", "/api/set_valve_states", {"2": "open"})
    rec.post("during safing: start step", "/api/start_step_execution", {"procedure_index": 0, "step_index": 2})
    rec.post("during safing: safe system again", "/api/safe_system")
    wait_until(lambda: is_idle(rec), "safe system 1 to finish")
    rec.snapshot("after safe system 1")

    # --- safe_system: no safe state's requirements met (valve 1 open, pressure 1 < 50) ---
    rec.post("safe system none: start", "/api/safe_system")
    wait_until(lambda: is_idle(rec), "safe system (no match) to finish")
    rec.snapshot("after safe system none")

    # --- After website shutdown ---
    website.shutdown()
    rec.get("shutdown: server status", "/api/get_server_status")
    rec.get("shutdown: heartbeat", "/api/send_heartbeat")
    rec.get("shutdown: valve info", "/api/get_valve_info")
    rec.get("shutdown: safe mode", "/api/get_safe_mode")
    rec.post("shutdown: set valve", "/api/set_valve_states", {"1": "open"})
    rec.post("shutdown: safe system", "/api/safe_system")
    rec.post("shutdown: start step", "/api/start_step_execution", {"procedure_index": 0, "step_index": 0})
    operations.shutdown()

    return rec.results


def is_safing(rec: Recorder) -> bool:
    return rec.client.get("/api/is_safing").get_json()["safing"]


def run_auto_safe_scenario(log_dir: str) -> list:
    """Safe mode auto-safe timer, using the shortest allowed timeout."""
    timeout = settings.WEBSITE_HEARTBEAT_TIMEOUT
    controller = Controller.from_config(load_config("controller_config.json", log_dir))
    operations, website = build_website(
        controller,
        load_config("website_config.json", log_dir, overrides={"safe_state_timeout": timeout}),
    )
    rec = Recorder(website, prefix="auto-safe: ")

    # 1) Timeout with nothing running: "Safe state 1" runs (opens valve 1, waits 2 s, opens valve 2).
    set_pressures(controller, {1: 25.0, 2: 50.0})
    rec.post("enable safe mode", "/api/set_safe_mode", {"safe_mode": True})
    wait_until(lambda: valve_state(rec, 1) == "open", "auto-safe to start", timeout=timeout + 5)
    rec.get("safe mode during auto-safe", "/api/get_safe_mode")
    rec.snapshot("during auto-safe")
    rec.post("during auto-safe: set valve", "/api/set_valve_states", {"2": "open"})
    rec.post("during auto-safe: safe system", "/api/safe_system")
    wait_until(lambda: is_idle(rec), "auto-safe to finish")
    rec.get("safe mode after auto-safe", "/api/get_safe_mode")
    rec.snapshot("after auto-safe")

    # 2) Timeout while a step is executing: safing waits for the step, then runs.
    #    Step 0/0 takes ~2 s; start it 1.5 s after enabling safe mode so the timeout lands mid-step.
    #    Pressure 75 selects "Safe state 2" (waits 5 s, opens valve 1, closes valve 2).
    rec.post("step+timeout: close valves", "/api/set_valve_states", {"1": "closed", "2": "closed"})
    set_pressures(controller, {1: 75.0, 2: 50.0})
    rec.post("step+timeout: enable safe mode", "/api/set_safe_mode", {"safe_mode": True})
    time.sleep(timeout / 2)
    rec.post("step+timeout: start step 0/0", "/api/start_step_execution", {"procedure_index": 0, "step_index": 0})
    wait_until(lambda: is_safing(rec), "auto-safe to start after step", timeout=timeout + 5)
    rec.snapshot("step+timeout: when safing starts")
    wait_until(lambda: is_idle(rec), "auto-safe to finish", timeout=10)
    rec.get("step+timeout: safe mode after", "/api/get_safe_mode")
    rec.snapshot("step+timeout: after")

    website.shutdown()
    operations.shutdown()
    return rec.results


def run_all() -> list:
    with tempfile.TemporaryDirectory() as log_dir:
        return run_main_scenarios(log_dir) + run_auto_safe_scenario(log_dir)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--record", action="store_true", help="Write a new baseline instead of comparing.")
    args = parser.parse_args()

    results = run_all()
    rendered = json.dumps(results, indent=2, sort_keys=True) + "\n"

    if args.record:
        os.makedirs(os.path.dirname(BASELINE_PATH), exist_ok=True)
        with open(BASELINE_PATH, "w") as f:
            f.write(rendered)
        print(f"Recorded {len(results)} requests to {os.path.relpath(BASELINE_PATH, ROOT)}")
        return 0

    if not os.path.exists(BASELINE_PATH):
        print(f"No baseline at {os.path.relpath(BASELINE_PATH, ROOT)}; run with --record first.")
        return 2
    with open(BASELINE_PATH) as f:
        baseline = f.read()
    if baseline == rendered:
        print(f"PASS: all {len(results)} requests match the baseline.")
        return 0
    diff = difflib.unified_diff(
        baseline.splitlines(keepends=True), rendered.splitlines(keepends=True),
        fromfile="baseline", tofile="current",
    )
    sys.stdout.writelines(diff)
    print("\nFAIL: responses differ from the baseline (see diff above).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
