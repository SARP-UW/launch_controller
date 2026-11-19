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
from src.operations import BusyError, InvalidValveStateError, StepSequenceError, ValveChangeError
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
    # Valve 1 open + valve 2 pulsed open breaks the demo rule {"open": [1, 2]}, so this needs force.
    h["set_valves"]({"1": "open", "2": "pulse:0.3", "operator": "alice", "force": "true"})
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
    # step waits 2 s; it opens valves 1 and 2 (an invalid state in the demo config), so it needs force
    h["start_step"]({"procedure_index": "0", "step_index": "0", "operator": "alice", "force": "true"})
    assert time.time() - started < 0.5

    executing = operations.get_procedure_status()["executing"]
    assert executing == {"procedure_index": 0, "step_index": 0, "user": "hub:alice"}
    with pytest.raises(BusyError, match=r"Cannot modify valves while step is executing \(by hub:alice\)"):
        h["set_valve"]({"valve_id": "2", "state": "open"})
    with pytest.raises(BusyError, match="Another step is already being executed"):
        h["start_step"]({"procedure_index": "0", "step_index": "2"})

    wait_until(lambda: is_idle(operations), "step to finish")
    assert operations.get_procedure_status()["completion"] == {"0": [0]}
    last = operations.get_last_step()
    assert last["last_step"]["result"] == "completed" and last["last_step"]["user"] == "hub:alice"
    assert (last["last_successful_step"]["procedure_index"], last["last_successful_step"]["step_index"]) == (0, 0)


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
    assert set(state) == {"valves", "sensors", "safe_mode", "safing", "procedure_status", "last_step"}
    assert state["last_step"] == {"last_step": None, "last_successful_step": None}
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


# --- Phase 4 #1: invalid valve states ---

def spoke_message(error: Exception) -> str:
    """The failure message spoke.py sends to the hub."""
    return f"{type(error).__name__}: {error}"


def test_invalid_valve_state_rejected_then_forced(system):
    operations, h = system
    h["set_valve"]({"valve_id": "1", "state": "open"})
    with pytest.raises(InvalidValveStateError) as excinfo:
        h["set_valve"]({"valve_id": "2", "state": "open", "operator": "bob"})
    message = spoke_message(excinfo.value)
    assert message.startswith("InvalidValveStateError: ") and message.count("InvalidValveStateError") == 1
    assert "valve 1 (Main Valve) open and valve 2 (Secondary Valve) open" in message
    assert excinfo.value.violations == ["valve 1 (Main Valve) open and valve 2 (Secondary Valve) open"]
    assert valve_states(operations)[2] == "closed"  # nothing changed

    h["set_valve"]({"valve_id": "2", "state": "open", "force": "true"})
    assert valve_states(operations) == {1: "open", 2: "open"}


def test_invalid_state_checks_pulse_toggled_state(system):
    operations, h = system
    h["set_valve"]({"valve_id": "1", "state": "open"})
    with pytest.raises(InvalidValveStateError):
        h["pulse_valve"]({"valve_id": "2", "duration": "0.3"})
    assert not any(v["is_pulsing"] for v in operations.get_valve_info())
    h["pulse_valve"]({"valve_id": "2", "duration": "0.3", "force": "true"})
    assert valve_states(operations)[2] == "open"


def test_invalid_batch_applies_nothing(system):
    operations, h = system
    with pytest.raises(InvalidValveStateError):
        h["set_valves"]({"1": "open", "2": "open"})
    assert valve_states(operations) == {1: "closed", 2: "closed"}


def test_valid_change_is_not_blocked(system):
    operations, h = system
    h["set_valves"]({"1": "open", "2": "closed"})
    assert valve_states(operations) == {1: "open", 2: "closed"}


def test_start_step_invalid_state_rejected_then_forced(system):
    operations, h = system
    with pytest.raises(InvalidValveStateError, match="valve 1 \\(Main Valve\\) open and valve 2"):
        h["start_step"]({"procedure_index": "0", "step_index": "0"})
    assert operations.get_procedure_status()["executing"] is None
    h["start_step"]({"procedure_index": "0", "step_index": "0", "force": "true"})
    assert operations.get_procedure_status()["executing"] is not None
    wait_until(lambda: is_idle(operations), "step to finish")


@pytest.mark.parametrize("command, args", [
    ("set_valve", {"valve_id": "1", "state": "open", "force": "maybe"}),
    ("start_step", {"procedure_index": "0", "step_index": "2", "force": "yes please"}),
])
def test_bad_force_arg(system, command, args):
    _, h = system
    with pytest.raises(ValueError, match="'force' must be 'true' or 'false'"):
        h[command](args)


def test_safe_system_ignores_invalid_states(system):
    operations, h = system
    h["safe_system"]({})  # "Safe state 1" opens valves 1 and 2: invalid, but safing is never checked
    wait_until(lambda: is_idle(operations), "safe system to finish")
    assert valve_states(operations) == {1: "open", 2: "open"}


# --- Phase 4 #2: last step and expected_last_step ---

def test_expected_last_step(system):
    operations, h = system
    with pytest.raises(StepSequenceError, match="last successful step is none"):
        h["start_step"]({"procedure_index": "0", "step_index": "2", "expected_last_step": "0:1"})
    assert operations.get_procedure_status()["executing"] is None

    h["start_step"]({"procedure_index": "0", "step_index": "2", "expected_last_step": "none"})  # 0.5 s pulse
    wait_until(lambda: is_idle(operations), "step 0:2 to finish")

    with pytest.raises(StepSequenceError) as excinfo:
        h["start_step"]({"procedure_index": "1", "step_index": "1", "expected_last_step": "none"})
    assert spoke_message(excinfo.value) == "StepSequenceError: last successful step is 0:2"
    h["start_step"]({"procedure_index": "1", "step_index": "1", "expected_last_step": " 0:2 "})
    wait_until(lambda: is_idle(operations), "step 1:1 to finish")
    assert operations.get_last_step()["last_successful_step"]["procedure_index"] == 1


@pytest.mark.parametrize("value", ["0", "a:b", "0:1:2", ""])
def test_bad_expected_last_step(system, value):
    _, h = system
    with pytest.raises(ValueError, match="'expected_last_step' must be 'P:S'"):
        h["start_step"]({"procedure_index": "0", "step_index": "2", "expected_last_step": value})


# --- Phase 4 #4: safing during a running step aborts it ---

def test_safe_system_aborts_running_step(system):
    operations, h = system
    # Procedure 1 step 0: open valve 1, wait 5 s, then [pulse 1, close 2]. Abort it during the 5 s wait.
    h["start_step"]({"procedure_index": "1", "step_index": "0", "operator": "alice"})
    wait_until(lambda: valve_states(operations)[1] == "open", "step's first action")
    started = time.time()
    h["safe_system"]({"operator": "bob"})
    assert time.time() - started < 0.5
    assert operations.get_safing_status() == {"safing": True, "user": "hub:bob"}
    with pytest.raises(BusyError, match="already being safed by hub:bob"):
        h["safe_system"]({})
    with pytest.raises(BusyError):  # blocked from the moment of the safe request (message names the step until it stops)
        h["set_valve"]({"valve_id": "2", "state": "open", "force": "true"})

    wait_until(lambda: operations.get_procedure_status()["executing"] is None, "step to stop", timeout=0.5)
    last = operations.get_last_step()
    assert last["last_step"]["result"] == "aborted"
    assert last["last_successful_step"] is None
    assert operations.get_procedure_status()["completion"] == {}
    # Valve 1 is open now, so "Safe state 1" doesn't match; none of the demo safe states do at 25 psi -> no action.
    wait_until(lambda: is_idle(operations), "safing to finish", timeout=1)
    assert valve_states(operations) == {1: "open", 2: "closed"}  # the step's later actions never ran


def test_safe_cancels_pending_pulse_return(system):
    operations, h = system
    h["pulse_valve"]({"valve_id": "2", "duration": "0.6"})
    assert valve_states(operations)[2] == "open"
    h["safe_system"]({})  # "Safe state 1" (valve 1 closed): opens 1, waits 2 s, opens 2
    time.sleep(1.0)  # past the pulse's return time
    assert valve_states(operations)[2] == "open"  # the return toggle was cancelled
    assert not any(v["is_pulsing"] for v in operations.get_valve_info())
    wait_until(lambda: is_idle(operations), "safing to finish")
    assert valve_states(operations) == {1: "open", 2: "open"}


def test_changes_while_already_invalid(system):
    operations, h = system
    h["set_valves"]({"1": "open", "2": "open", "force": "true"})  # now in the invalid state
    # A change that won't apply reports its own error, not the invalid state.
    with pytest.raises(RuntimeError, match="Controller has no valve with ID: 99"):
        h["set_valve"]({"valve_id": "99", "state": "open"})
    with pytest.raises(ValveChangeError) as excinfo:
        h["set_valves"]({"1": "sideways"})
    assert excinfo.value.failed == {"1": "Invalid valve action: sideways"}
    # Like app.js, the full resulting state is checked: a change that leaves it invalid needs force ...
    with pytest.raises(InvalidValveStateError):
        h["set_valve"]({"valve_id": "1", "state": "open"})
    # ... and a change that fixes it does not.
    h["set_valve"]({"valve_id": "2", "state": "closed"})
    assert valve_states(operations) == {1: "open", 2: "closed"}
