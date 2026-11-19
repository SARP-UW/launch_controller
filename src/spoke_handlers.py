"""
Spoke command handlers: the hub-facing commands of the launch controller.

Each handler follows the spoke.py contract:
    - takes one argument, the command's args: a dict of strings
    - returns a dict (sent back to the hub as `data`) or None
    - raises an exception to fail the command (the exception text goes back to the hub)
    - runs one at a time, so it must return quickly: anything that waits (steps, safe system,
      pulses) runs in a background thread inside ControllerOperations

Every handler accepts an optional `operator` argument; it is recorded in the logs as "hub:<operator>"
(or just "hub" when omitted). Unknown arguments are rejected, so a typo fails loudly instead of being ignored.

Commands ([...] = optional):
    set_valve            {valve_id, state, [force]}                 state: "open" | "closed"
    pulse_valve          {valve_id, duration, [force]}              duration in seconds, > 0
    set_valves           {<valve_id>: <action>, ..., [force]}       action: "open" | "closed" | "pulse:<seconds>"
    safe_system          {}                                         returns right away; aborts a running step
    set_safe_mode        {enabled}                                  enabled: "true" | "false"
    start_step           {procedure_index, step_index,              returns right away; runs in a thread
                          [force], [expected_last_step]}            expected_last_step: "P:S" | "none"
    set_step_completion  {procedure_index, step_index, completed}   completed: "true" | "false"
    reset_procedure      {procedure_index}
    get_state            {}                                         live valves, sensors, safe mode, safing, procedure status
    get_config           {}                                         valve/sensor names and ranges, procedures, safe states, ...

Numbers in returned data reach the hub as floats (protobuf Struct), so ids come back as e.g. 3.0.

Invalid valve states: set_valve, pulse_valve, set_valves and start_step are checked against invalid_valve_states.
A change that would break a rule fails with a message starting "InvalidValveStateError:" and changes nothing.
After the operator confirms, resend the same command with force="true". safe_system is never checked.

Step sequence: start_step with expected_last_step ("P:S" for the step the hub believes last completed, or "none")
fails with "StepSequenceError: last successful step is P:S" and runs nothing if the controller disagrees.
The controller's last step is in telemetry (last_step_*, last_successful_*).
"""
from typing import Callable, Dict, Optional
from .operations import ControllerOperations, ValveChangeError, NOT_CHECKED

# Argument accepted by every command, for logging who sent it.
OPERATOR_ARG = "operator"

# Optional argument of valve and step commands: apply even if it causes an invalid valve state.
FORCE_ARG = "force"

Args = Dict[str, str]
Handler = Callable[[Args], Optional[dict]]


def _user(args: Args) -> str:
    """
    Name recorded in the logs for a hub command.
    """
    operator = args.get(OPERATOR_ARG, "").strip()
    return f"hub:{operator}" if operator else "hub"


def _check_args(args: Args, required: tuple, optional: tuple = ()) -> None:
    """
    Raises ValueError if a required argument is missing or an unknown argument is present.
    """
    missing = [name for name in required if name not in args]
    if missing:
        raise ValueError(f"Missing argument(s): {', '.join(missing)}")
    allowed = set(required) | set(optional) | {OPERATOR_ARG}
    unknown = sorted(set(args) - allowed)
    if unknown:
        raise ValueError(f"Unknown argument(s): {', '.join(unknown)}")


def _parse_int(args: Args, name: str) -> int:
    try:
        return int(args[name].strip())
    except ValueError:
        raise ValueError(f"'{name}' must be an integer, got: {args[name]!r}")


def _parse_float(args: Args, name: str) -> float:
    try:
        return float(args[name].strip())
    except ValueError:
        raise ValueError(f"'{name}' must be a number, got: {args[name]!r}")


def _parse_bool(args: Args, name: str) -> bool:
    value = args[name].strip().lower()
    if value in ("true", "1", "yes"):
        return True
    if value in ("false", "0", "no"):
        return False
    raise ValueError(f"'{name}' must be 'true' or 'false', got: {args[name]!r}")


def _parse_force(args: Args) -> bool:
    return _parse_bool(args, FORCE_ARG) if FORCE_ARG in args else False


def _parse_expected_last_step(args: Args) -> object:
    """
    Parses start_step's optional expected_last_step: "P:S" -> (P, S), "none" -> None, absent -> NOT_CHECKED.
    """
    if "expected_last_step" not in args:
        return NOT_CHECKED
    value = args["expected_last_step"].strip().lower()
    if value == "none":
        return None
    try:
        procedure_index, step_index = value.split(":")
        return (int(procedure_index), int(step_index))
    except ValueError:
        raise ValueError(f"'expected_last_step' must be 'P:S' (e.g. '0:2') or 'none', got: {args['expected_last_step']!r}")


def _parse_valve_state(args: Args, name: str) -> str:
    value = args[name].strip().lower()
    if value not in ("open", "closed"):
        raise ValueError(f"'{name}' must be 'open' or 'closed', got: {args[name]!r}")
    return value


def make_handlers(operations: ControllerOperations) -> Dict[str, Handler]:
    """
    Builds the command name -> handler dict to pass to Spoke().

    Args:
        operations: The ControllerOperations object the commands act on (shared with the website, if running).
    """

    def apply_single_valve_change(valve_id: int, action: str, user: str, force: bool) -> None:
        """Applies one valve change, raising with that valve's error message if it fails.
        InvalidValveStateError passes through unchanged, so the hub sees its prefix."""
        try:
            operations.set_valve_states({str(valve_id): action}, user, force=force)
        except ValveChangeError as e:
            raise RuntimeError(next(iter(e.failed.values())))

    def set_valve(args: Args) -> None:
        _check_args(args, ("valve_id", "state"), (FORCE_ARG,))
        valve_id = _parse_int(args, "valve_id")
        state = _parse_valve_state(args, "state")
        apply_single_valve_change(valve_id, state, _user(args), _parse_force(args))

    def pulse_valve(args: Args) -> None:
        _check_args(args, ("valve_id", "duration"), (FORCE_ARG,))
        valve_id = _parse_int(args, "valve_id")
        duration = _parse_float(args, "duration")
        if duration <= 0:
            raise ValueError(f"'duration' must be positive, got: {duration}")
        apply_single_valve_change(valve_id, f"pulse:{duration}", _user(args), _parse_force(args))

    def set_valves(args: Args) -> None:
        changes = {key: value for key, value in args.items() if key not in (OPERATOR_ARG, FORCE_ARG)}
        if not changes:
            raise ValueError("No valve changes given (expected args like {'1': 'open', '2': 'pulse:0.5'})")
        # ValveChangeError (some valves failed, the rest applied) propagates; its message lists each failure.
        # InvalidValveStateError (nothing applied) propagates too.
        operations.set_valve_states(changes, _user(args), force=_parse_force(args))

    def safe_system(args: Args) -> None:
        _check_args(args, ())
        operations.safe_system(_user(args))

    def set_safe_mode(args: Args) -> None:
        _check_args(args, ("enabled",))
        operations.set_safe_mode(_parse_bool(args, "enabled"), _user(args))

    def start_step(args: Args) -> None:
        _check_args(args, ("procedure_index", "step_index"), (FORCE_ARG, "expected_last_step"))
        operations.start_step(
            _parse_int(args, "procedure_index"),
            _parse_int(args, "step_index"),
            _user(args),
            force=_parse_force(args),
            expected_last_step=_parse_expected_last_step(args),
        )

    def set_step_completion(args: Args) -> None:
        _check_args(args, ("procedure_index", "step_index", "completed"))
        operations.set_step_completion(
            _parse_int(args, "procedure_index"),
            _parse_int(args, "step_index"),
            _parse_bool(args, "completed"),
            _user(args),
        )

    def reset_procedure(args: Args) -> None:
        _check_args(args, ("procedure_index",))
        operations.reset_procedure(_parse_int(args, "procedure_index"), _user(args))

    def get_state(args: Args) -> dict:
        _check_args(args, ())
        return operations.get_status()

    def get_config(args: Args) -> dict:
        _check_args(args, ())
        return operations.get_config()

    return {
        "set_valve": set_valve,
        "pulse_valve": pulse_valve,
        "set_valves": set_valves,
        "safe_system": safe_system,
        "set_safe_mode": set_safe_mode,
        "start_step": start_step,
        "set_step_completion": set_step_completion,
        "reset_procedure": reset_procedure,
        "get_state": get_state,
        "get_config": get_config,
    }
