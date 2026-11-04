"""
Telemetry: the flat dict of live state the spoke publishes to the hub every tick.

The full state goes out every tick (not just changes), since telemetry can be dropped: the hub UI should never
depend on any single message. The key set is the same every tick, so a key never disappears between messages.
Values are scalars only (float, str, bool), with -1 standing in for "none" on indices.

Keys (N = valve/sensor id from config, P = procedure index, S = step index):
    pt_N                     float   latest pressure reading of sensor N
    valve_N                  str     "open" | "closed"
    valve_N_pulse_remaining  float   seconds left in the current pulse (0.0 when not pulsing)
    safe_mode                bool    safe mode enabled
    safing                   bool    the system is being safed (manual or auto)
    step_executing           bool    a procedure step is executing
    step_procedure_index     int     procedure of the executing step (-1 when idle)
    step_index               int     index of the executing step (-1 when idle)
    proc_P_step_S_done       bool    step S of procedure P is marked complete

Names, ranges and procedure/step titles are static and come from the get_config command instead.
"""
from typing import Dict, Union

from .operations import ControllerOperations

Value = Union[float, str, bool]


def build_telemetry(operations: ControllerOperations) -> Dict[str, Value]:
    """
    Builds one telemetry sample from the current state of the operations object.
    """
    status = operations.get_status()
    values: Dict[str, Value] = {}

    for sensor in status["sensors"]:
        values[f"pt_{sensor['id']}"] = float(sensor["current_pressure"])

    for valve in status["valves"]:
        values[f"valve_{valve['id']}"] = valve["current_state"]
        values[f"valve_{valve['id']}_pulse_remaining"] = float(valve.get("pulse_remaining", 0.0))

    values["safe_mode"] = status["safe_mode"]
    values["safing"] = status["safing"]["safing"]

    executing = status["procedure_status"]["executing"]
    values["step_executing"] = executing is not None
    values["step_procedure_index"] = executing["procedure_index"] if executing else -1
    values["step_index"] = executing["step_index"] if executing else -1

    completion = status["procedure_status"]["completion"]
    for procedure_index, procedure in enumerate(operations.procedures):
        done = completion.get(str(procedure_index), [])
        for step_index in range(len(procedure["steps"])):
            values[f"proc_{procedure_index}_step_{step_index}_done"] = step_index in done

    return values
