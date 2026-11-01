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

Commands:
    set_valve            {valve_id, state}                          state: "open" | "closed"
    pulse_valve          {valve_id, duration}                       duration in seconds, > 0
    set_valves           {<valve_id>: <action>, ...}                action: "open" | "closed" | "pulse:<seconds>"
    safe_system          {}                                         returns right away; runs in a thread
    set_safe_mode        {enabled}                                  enabled: "true" | "false"
    start_step           {procedure_index, step_index}              returns right away; runs in a thread
    set_step_completion  {procedure_index, step_index, completed}   completed: "true" | "false"
    reset_procedure      {procedure_index}
    get_state            {}                                         live valves, sensors, safe mode, safing, procedure status
    get_config           {}                                         valve/sensor names and ranges, procedures, safe states, ...

Numbers in returned data reach the hub as floats (protobuf Struct), so ids come back as e.g. 3.0.
"""
from typing import Callable, Dict, Optional
from .operations import ControllerOperations, ValveChangeError

# Argument accepted by every command, for logging who sent it.
OPERATOR_ARG = "operator"

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

    def apply_single_valve_change(valve_id: int, action: str, user: str) -> None:
        """Applies one valve change, raising with that valve's error message if it fails."""
        try:
            operations.set_valve_states({str(valve_id): action}, user)
        except ValveChangeError as e:
            raise RuntimeError(next(iter(e.failed.values())))

    def set_valve(args: Args) -> None:
        _check_args(args, ("valve_id", "state"))
        valve_id = _parse_int(args, "valve_id")
        state = _parse_valve_state(args, "state")
        apply_single_valve_change(valve_id, state, _user(args))

    def pulse_valve(args: Args) -> None:
        _check_args(args, ("valve_id", "duration"))
        valve_id = _parse_int(args, "valve_id")
        duration = _parse_float(args, "duration")
        if duration <= 0:
            raise ValueError(f"'duration' must be positive, got: {duration}")
        apply_single_valve_change(valve_id, f"pulse:{duration}", _user(args))

    def set_valves(args: Args) -> None:
        changes = {key: value for key, value in args.items() if key != OPERATOR_ARG}
        if not changes:
            raise ValueError("No valve changes given (expected args like {'1': 'open', '2': 'pulse:0.5'})")
        # ValveChangeError (some valves failed, the rest applied) propagates; its message lists each failure.
        operations.set_valve_states(changes, _user(args))

    def safe_system(args: Args) -> None:
        _check_args(args, ())
        operations.safe_system(_user(args))

    def set_safe_mode(args: Args) -> None:
        _check_args(args, ("enabled",))
        operations.set_safe_mode(_parse_bool(args, "enabled"), _user(args))

    def start_step(args: Args) -> None:
        _check_args(args, ("procedure_index", "step_index"))
        operations.start_step(_parse_int(args, "procedure_index"), _parse_int(args, "step_index"), _user(args))

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
