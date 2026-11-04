"""
Tests for the telemetry sample (src/telemetry.py) the spoke publishes every tick.
Uses config/demo in MOCK_MODE with pinned sensor pressures (see smoke_test_website.py).

Run from the launch_controller folder:
    .venv/bin/python -m pytest tests/test_telemetry.py
"""
import pytest
from google.protobuf.struct_pb2 import Struct

from smoke_test_website import Controller, ControllerOperations, load_config, set_pressures, wait_until
from src.telemetry import build_telemetry


@pytest.fixture
def operations(tmp_path):
    controller = Controller.from_config(load_config("controller_config.json", str(tmp_path)))
    operations = ControllerOperations.from_config(controller, load_config("website_config.json", str(tmp_path)))
    set_pressures(controller, {1: 25.0, 2: 50.0})
    yield operations
    operations.shutdown()


def is_idle(operations):
    return operations.get_procedure_status()["executing"] is None and not operations.get_safing_status()["safing"]


def test_idle_sample(operations):
    t = build_telemetry(operations)
    assert t["pt_1"] == 25.0 and t["pt_2"] == 50.0
    assert t["valve_1"] in ("open", "closed")
    assert t["valve_1_pulse_remaining"] == 0.0
    assert t["safe_mode"] is False and t["safing"] is False
    assert t["step_executing"] is False
    assert t["step_procedure_index"] == -1 and t["step_index"] == -1
    assert t["proc_0_step_0_done"] is False


def test_values_are_scalars_and_survive_struct(operations):
    t = build_telemetry(operations)
    assert all(isinstance(v, (bool, int, float, str)) for v in t.values())
    struct = Struct()
    struct.update(t)  # what Spoke.publish does
    assert dict(struct) == t


def test_key_set_stable_during_pulse_and_step(operations):
    idle_keys = set(build_telemetry(operations))

    operations.set_valve_states({"2": "pulse:0.5"}, "test")
    pulsing = build_telemetry(operations)
    assert set(pulsing) == idle_keys
    assert 0.0 < pulsing["valve_2_pulse_remaining"] <= 0.5
    wait_until(lambda: build_telemetry(operations)["valve_2_pulse_remaining"] == 0.0, "pulse to end")

    operations.start_step(0, 0, "test")  # step contains a 2 s wait
    executing = build_telemetry(operations)
    assert set(executing) == idle_keys
    assert executing["step_executing"] is True
    assert executing["step_procedure_index"] == 0 and executing["step_index"] == 0
    wait_until(lambda: is_idle(operations), "step to finish")

    done = build_telemetry(operations)
    assert set(done) == idle_keys
    assert done["step_executing"] is False
    assert done["proc_0_step_0_done"] is True


def test_safe_mode_and_safing(operations):
    operations.set_safe_mode(True, "test")
    assert build_telemetry(operations)["safe_mode"] is True
    operations.safe_system("test")
    assert build_telemetry(operations)["safing"] is True
    wait_until(lambda: is_idle(operations), "safing to finish")
    assert build_telemetry(operations)["safing"] is False
