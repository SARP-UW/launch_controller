"""
Tests for the spoke command handlers (src/spoke_handlers.py), called directly with string args the way
spoke.py calls them. Uses config/demo in MOCK_MODE with pinned sensor pressures (see smoke_test_website.py).

Run from the launch_controller folder:
    .venv/bin/python -m pytest tests/test_spoke_handlers.py
"""
import time

import pytest
from google.protobuf.struct_pb2 import Struct

# Importing the smoke test applies the shared test setup: MOCK_MODE, quiet prints, pinned pressures.
from smoke_test_website import Controller, ControllerOperations, load_config, set_pressures, wait_until
from src.operations import BusyError, ValveChangeError
from src.spoke_handlers import make_handlers


@pytest.fixture
def system(tmp_path):
    controller = Controller.from_config(load_config("controller_config.json", str(tmp_path)))
    operations = ControllerOperations.from_config(controller, load_config("website_config.json", str(tmp_path)))
    set_pressures(controller, {1: 25.0, 2: 50.0})
    yield operations, make_handlers(operations)
    operations.shutdown()


def valve_states(operations):
    return {v["id"]: v["current_state"] for v in operations.get_valve_info()}


def is_idle(operations):
    return operations.get_procedure_status()["executing"] is None and not operations.get_safing_status()["safing"]


def to_struct(data: dict) -> dict:
    """Round-trips data through a protobuf Struct, as spoke.py does when replying to the hub."""
    struct = Struct()
    struct.update(data)
    return dict(struct)


# --- Valves ---

def test_set_valve(system):
    operations, h = system
    assert h["set_valve"]({"valve_id": "1", "state": "open"}) is None
    assert valve_states(operations)[1] == "open"
    h["set_valve"]({"valve_id": " 1 ", "state": "CLOSED"})
    assert valve_states(operations)[1] == "closed"


@pytest.mark.parametrize("args, error", [
    ({"state": "open"}, "Missing argument(s): valve_id"),
    ({"valve_id": "1"}, "Missing argument(s): state"),
    ({"valve_id": "1", "state": "open", "colour": "red"}, "Unknown argument(s): colour"),
    ({"valve_id": "one", "state": "open"}, "'valve_id' must be an integer"),
    ({"valve_id": "1", "state": "sideways"}, "'state' must be 'open' or 'closed'"),
    ({"valve_id": "1", "state": "pulse:1"}, "'state' must be 'open' or 'closed'"),
])
def test_set_valve_bad_args(system, args, error):
    _, h = system
    with pytest.raises(ValueError, match=error.replace("(", r"\(").replace(")", r"\)")):
        h["set_valve"](args)


def test_set_valve_unknown_valve(system):
    _, h = system
    with pytest.raises(RuntimeError, match="Controller has no valve with ID: 99"):
        h["set_valve"]({"valve_id": "99", "state": "open"})


def test_pulse_valve(system):
    operations, h = system
    h["pulse_valve"]({"valve_id": "2", "duration": "0.3"})
    info = {v["id"]: v for v in operations.get_valve_info()}
    assert info[2]["is_pulsing"] and info[2]["current_state"] == "open"
    with pytest.raises(RuntimeError, match="Valve 2 is currently pulsing"):
        h["set_valve"]({"valve_id": "2", "state": "closed"})
    wait_until(lambda: not any(v["is_pulsing"] for v in operations.get_valve_info()), "pulse to end")
    assert valve_states(operations)[2] == "closed"


@pytest.mark.parametrize("duration", ["0", "-1", "abc"])
def test_pulse_valve_bad_duration(system, duration):
    _, h = system
    with pytest.raises(ValueError, match="'duration' must be"):
        h["pulse_valve"]({"valve_id": "2", "duration": duration})


def test_set_valves_batch(system):
    operations, h = system
    h["set_valves"]({"1": "open", "2": "pulse:0.3", "operator": "alice"})
    states = valve_states(operations)
    assert states == {1: "open", 2: "open"}


def test_set_valves_partial_failure(system):
    operations, h = system
    with pytest.raises(ValveChangeError) as excinfo:
        h["set_valves"]({"1": "open", "99": "open", "2": "sideways"})
    assert set(excinfo.value.failed) == {"99", "2"}
    assert valve_states(operations)[1] == "open"  # the valid change was still applied


def test_set_valves_empty(system):
    _, h = system
    with pytest.raises(ValueError, match="No valve changes given"):
        h["set_valves"]({"operator": "alice"})


# --- Steps, safing, and what they block ---

def test_start_step_returns_immediately_and_blocks_valves(system):
    operations, h = system
    started = time.time()
    h["start_step"]({"procedure_index": "0", "step_index": "0", "operator": "alice"})  # step waits 2 s
    assert time.time() - started < 0.5

    executing = operations.get_procedure_status()["executing"]
    assert executing == {"procedure_index": 0, "step_index": 0, "user": "hub:alice"}
    with pytest.raises(BusyError, match=r"Cannot modify valves while step is executing \(by hub:alice\)"):
        h["set_valve"]({"valve_id": "2", "state": "open"})
    with pytest.raises(BusyError, match="Another step is already being executed"):
        h["start_step"]({"procedure_index": "0", "step_index": "2"})
    with pytest.raises(BusyError, match="Cannot safe system while step is executing"):
        h["safe_system"]({})

    wait_until(lambda: is_idle(operations), "step to finish")
    assert operations.get_procedure_status()["completion"] == {"0": [0]}


@pytest.mark.parametrize("args, error", [
    ({"procedure_index": "9", "step_index": "0"}, "Invalid procedure index: 9"),
    ({"procedure_index": "0", "step_index": "9"}, "Invalid step index: 9"),
    ({"procedure_index": "x", "step_index": "0"}, "'procedure_index' must be an integer"),
    ({"procedure_index": "0"}, r"Missing argument\(s\): step_index"),
])
def test_start_step_bad_args(system, args, error):
    _, h = system
    with pytest.raises(ValueError, match=error):
        h["start_step"](args)


def test_safe_system_returns_immediately(system):
    operations, h = system
    started = time.time()
    h["safe_system"]({})  # "Safe state 1" waits 2 s
    assert time.time() - started < 0.5
    assert operations.get_safing_status() == {"safing": True, "user": "hub"}
    with pytest.raises(BusyError, match=r"Cannot modify valves while system is being safed \(by hub\)"):
        h["set_valve"]({"valve_id": "2", "state": "open"})
    wait_until(lambda: is_idle(operations), "safe system to finish")
    assert valve_states(operations) == {1: "open", 2: "open"}


def test_set_safe_mode(system):
    operations, h = system
    h["set_safe_mode"]({"enabled": "true"})
    assert operations.get_safe_mode() is True
    h["set_safe_mode"]({"enabled": "False"})
    assert operations.get_safe_mode() is False
    with pytest.raises(ValueError, match="'enabled' must be 'true' or 'false'"):
        h["set_safe_mode"]({"enabled": "maybe"})


def test_step_completion_and_reset(system):
    operations, h = system
    h["set_step_completion"]({"procedure_index": "0", "step_index": "1", "completed": "true"})
    h["set_step_completion"]({"procedure_index": "1", "step_index": "0", "completed": "true"})
    assert operations.get_procedure_status()["completion"] == {"0": [1], "1": [0]}
    h["reset_procedure"]({"procedure_index": "0"})
    assert operations.get_procedure_status()["completion"] == {"1": [0]}
    with pytest.raises(ValueError, match="Invalid procedure index: 5"):
        h["reset_procedure"]({"procedure_index": "5"})


# --- Queries ---

def test_get_state_survives_struct(system):
    operations, h = system
    h["pulse_valve"]({"valve_id": "2", "duration": "0.3"})
    h["set_step_completion"]({"procedure_index": "0", "step_index": "1", "completed": "true"})
    state = to_struct(h["get_state"]({}))
    assert set(state) == {"valves", "sensors", "safe_mode", "safing", "procedure_status"}
    valves = {v["id"]: v for v in state["valves"]}
    assert valves[2.0]["is_pulsing"] is True and valves[2.0]["pulse_duration"] == 0.3
    assert state["safing"]["user"] is None
    assert state["procedure_status"]["executing"] is None
    assert list(state["procedure_status"]["completion"]["0"]) == [1.0]


def test_get_config_survives_struct(system):
    _, h = system
    config = to_struct(h["get_config"]({}))
    assert [v["name"] for v in config["valves"]] == ["Main Valve", "Secondary Valve"]
    assert config["sensors"][0]["max_pressure"] == 1000.0
    assert config["procedures"][0]["name"] == "Startup Sequence"
    # grouped (simultaneous) actions are nested lists
    grouped = config["procedures"][1]["steps"][0]["actions"][2]
    assert [a["type"] for a in grouped] == ["pulse_valve", "set_valve"]


@pytest.mark.parametrize("command", ["safe_system", "get_state", "get_config"])
def test_no_arg_commands_reject_unknown_args(system, command):
    _, h = system
    with pytest.raises(ValueError, match="Unknown argument"):
        h[command]({"force": "true"})
