import time
import threading
from typing import Dict, List, Optional
from .controller import Controller
from .valve import ValveState
from .logger import Logger
from . import settings

# Minimum permissable safe state timeout in seconds
MIN_SAFE_STATE_TIMEOUT = 0.1

# Maximum permissable safe state timeout in seconds
MAX_SAFE_STATE_TIMEOUT = 1000.0


class OperationsError(Exception):
    """
    Base class for errors raised by ControllerOperations.
    """


class BusyError(OperationsError):
    """
    Raised when an operation is rejected because a step is executing or the system is being safed.

    Attributes:
        details: Extra info about what is blocking the operation (e.g. {"executing": {...}} or {"safing": {...}}).
    """
    def __init__(self, message: str, details: Optional[Dict] = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ValveChangeError(OperationsError):
    """
    Raised by set_valve_states when one or more valve changes failed. Changes that succeeded are still applied.

    Attributes:
        failed: Dict of valve id (as given) -> error message.
    """
    def __init__(self, failed: Dict[str, str]) -> None:
        super().__init__(f"Failed to change valves: {failed}")
        self.failed = failed


class OperationsShutdownError(OperationsError):
    """
    Raised when an operation is attempted after ControllerOperations has been shut down.
    """
    def __init__(self) -> None:
        super().__init__("Controller operations have been shut down")


class ControllerOperations:
    """
    Controller logic shared by every interface (website, spoke): safe mode and its auto-safe timer,
    safe states, procedures and step execution, and the rules that block valve changes while a step
    runs or the system is being safed.

    Methods raise exceptions instead of returning status codes:
        ValueError: invalid argument (e.g. procedure index out of range).
        BusyError: blocked by a running step or safe-system operation.
        ValveChangeError: some valve changes in set_valve_states failed.
        OperationsShutdownError: called after shutdown().
    """

    def _check_safe_state_requirement(self, requirement: Dict) -> bool:
        """
        Checks if a single safe state requirement is currently met.
        Used for both automatic safe mode timeout and manual safe system operations.
        
        Args:
            requirement: Dict containing requirement type and parameters.
            
        Returns:
            True if the requirement is met, False otherwise.
        """
        req_type = requirement.get("type")
        
        if req_type == "pressure_below":
            sensor_id = int(requirement["sensor_id"])
            threshold = float(requirement["threshold"])
            for sensor in self._controller.pressure_sensor_info:
                if int(sensor["id"]) == sensor_id:
                    current_pressure = float(sensor.get("current_pressure", 0))
                    return current_pressure < threshold
            return False
            
        elif req_type == "pressure_above":
            sensor_id = int(requirement["sensor_id"])
            threshold = float(requirement["threshold"])
            for sensor in self._controller.pressure_sensor_info:
                if int(sensor["id"]) == sensor_id:
                    current_pressure = float(sensor.get("current_pressure", 0))
                    return current_pressure > threshold
            return False
            
        elif req_type == "pressure_between":
            sensor_id = int(requirement["sensor_id"])
            min_threshold = float(requirement["min_threshold"])
            max_threshold = float(requirement["max_threshold"])
            for sensor in self._controller.pressure_sensor_info:
                if int(sensor["id"]) == sensor_id:
                    current_pressure = float(sensor.get("current_pressure", 0))
                    return min_threshold <= current_pressure <= max_threshold
            return False
            
        elif req_type == "valve_state":
            valve_id = int(requirement["valve_id"])
            required_state = requirement["state"].lower()
            for valve in self._controller.valve_info:
                if int(valve["id"]) == valve_id:
                    current_state = valve.get("current_state", "").lower()
                    return current_state == required_state
            return False
            
        elif req_type == "custom_message":
            # Custom messages are ignored for safe state selection - always considered met
            return True
            
        return False
    
    def _monitor_safe_mode(self) -> None:
        """
        Background thread method that safes the system when safe mode times out. Uses the same path as the
        manual safe system command, so valve changes and steps are blocked and "safing" is reported while it
        runs. If a step is executing when the timeout is reached, safing starts as soon as the step finishes.
        """
        interval = 1.0 / settings.WEBSITE_THREAD_UPDATE_RATE
        waiting_for_step = False
        while True:
            with self._thread_lock:
                if self._shutdown_flag:
                    break
                try:
                    if self._safe_mode and (time.time() - self._last_user_heartbeat) > self._safe_state_timeout:
                        if self._safing_system is not None:
                            # Already being safed (e.g. manually); nothing more to do.
                            self._safe_mode = False
                            waiting_for_step = False
                        elif self._currently_executing is not None:
                            if not waiting_for_step:
                                if settings.PRINT_WEBSITE_STATUS:
                                    print(f"WEBSITE STATUS: Safe mode timeout reached, waiting for executing step to finish before safing.")
                                self._logger.log_data(["system", "status", "Safe mode timeout reached, waiting for executing step to finish"])
                                waiting_for_step = True
                        else:
                            if settings.PRINT_WEBSITE_STATUS:
                                print(f"WEBSITE STATUS: Safe mode timeout reached, executing safe state.")
                            self._logger.log_data(["system", "status", "Safing system"])
                            self._safe_mode = False
                            waiting_for_step = False
                            self._start_safe_system_locked("system")
                    else:
                        waiting_for_step = False
                except Exception as e:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: Safe mode monitor error: {e}")
            time.sleep(interval)

    def _execute_actions(self, actions: List, user: str = "system") -> bool:
        """
        Executes a list of actions (supports both single and grouped/multi actions).
        
        Args:
            actions: List of action dicts or grouped action lists.
            user: The user/source executing the actions (for logging).
            
        Returns:
            True if all actions executed successfully, False if aborted (e.g., due to shutdown).
        """
        def execute_single_action(action: Dict) -> None:
            """Executes a single action (set_valve, pulse_valve, or wait)."""
            action_type = action.get("type")
            
            if action_type == "set_valve":
                valve_id = action.get("valve_id")
                state_str = action.get("state", "").lower()
                state = ValveState.OPEN if state_str == "open" else ValveState.CLOSED
                self._controller.set_valve(valve_id, state)
                if settings.PRINT_WEBSITE_STATUS:
                    print(f"WEBSITE STATUS: {user} executed set_valve: valve {valve_id} -> {state_str}")
                self._logger.log_data([user, "action", f"Set valve {valve_id} to {state_str}"])
                
            elif action_type == "pulse_valve":
                valve_id = action.get("valve_id")
                duration = float(action.get("duration", 1.0))
                self._controller.pulse_valve(valve_id, duration)
                if settings.PRINT_WEBSITE_STATUS:
                    print(f"WEBSITE STATUS: {user} executed pulse_valve: valve {valve_id} for {duration}s")
                self._logger.log_data([user, "action", f"Pulsed valve {valve_id} for {duration}s"])
                time.sleep(duration)
                
            elif action_type == "wait":
                duration = float(action.get("duration", 1.0))
                if settings.PRINT_WEBSITE_STATUS:
                    print(f"WEBSITE STATUS: {user} executing wait: {duration}s")
                time.sleep(duration)
                
            else:
                if settings.PRINT_WEBSITE_ERRORS:
                    print(f"WEBSITE ERROR: Unknown action type: {action_type}")

        def execute_multi_action(actions: List[Dict]) -> None:
            """Executes multiple actions simultaneously (all valve operations start together, then wait for longest duration)."""
            max_wait_duration = 0
            
            for action in actions:
                action_type = action.get("type")
                
                if action_type == "set_valve":
                    valve_id = action.get("valve_id")
                    state_str = action.get("state", "").lower()
                    state = ValveState.OPEN if state_str == "open" else ValveState.CLOSED
                    self._controller.set_valve(valve_id, state)
                    if settings.PRINT_WEBSITE_STATUS:
                        print(f"WEBSITE STATUS: {user} executed set_valve (multi): valve {valve_id} -> {state_str}")
                    self._logger.log_data([user, "action", f"Set valve {valve_id} to {state_str} (multi)"])
                    
                elif action_type == "pulse_valve":
                    valve_id = action.get("valve_id")
                    duration = float(action.get("duration", 1.0))
                    self._controller.pulse_valve(valve_id, duration)
                    if settings.PRINT_WEBSITE_STATUS:
                        print(f"WEBSITE STATUS: {user} executed pulse_valve (multi): valve {valve_id} for {duration}s")
                    self._logger.log_data([user, "action", f"Pulsed valve {valve_id} for {duration}s (multi)"])
                    max_wait_duration = max(max_wait_duration, duration)
                    
                elif action_type == "wait":
                    duration = float(action.get("duration", 1.0))
                    max_wait_duration = max(max_wait_duration, duration)
            
            # Wait for the longest action to complete
            if max_wait_duration > 0:
                time.sleep(max_wait_duration)

        try:
            for action in actions:
                # Check for shutdown
                if self._shutdown_flag:
                    return False
                
                # Handle multi-action (array of actions to execute simultaneously)
                if isinstance(action, list):
                    execute_multi_action(action)
                else:
                    execute_single_action(action)
            return True
        except Exception as e:
            if settings.PRINT_WEBSITE_ERRORS:
                print(f"WEBSITE ERROR: Action execution failed: {e}")
            self._logger.log_data([user, "error", f"Action execution failed: {e}"])
            return False

    def __init__(self, controller: Controller, safe_state_timeout: float, system_safe_states: List[dict], invalid_valve_states: List[dict], procedures: List[dict], logger: Logger) -> None:
        """
        Initializes a ControllerOperations object and starts the safe mode monitor thread.

        Args:
            controller: The Controller object to operate.
            safe_state_timeout: The time (in seconds) after which the system is put into a safe state once safe mode is enabled.
            system_safe_states: List of dicts defining safe states with requirements and actions.
            invalid_valve_states: List of dicts defining invalid valve states.
            procedures: List of dicts defining procedures that can be executed.
            logger: Logger used for operation status/action/error logging (columns: user, type, status).
        """
        if controller is None:
            raise ValueError("Invalid controller object")
        if safe_state_timeout < MIN_SAFE_STATE_TIMEOUT:
            raise ValueError(f"Safe state timeout is invalid: {safe_state_timeout} < {MIN_SAFE_STATE_TIMEOUT}")
        if safe_state_timeout > MAX_SAFE_STATE_TIMEOUT:
            raise ValueError(f"Safe state timeout is invalid: {safe_state_timeout} > {MAX_SAFE_STATE_TIMEOUT}")
        if safe_state_timeout < settings.WEBSITE_HEARTBEAT_TIMEOUT:
            raise ValueError(f"Safe state timeout is less than heartbeat timeout: {safe_state_timeout} s < {settings.WEBSITE_HEARTBEAT_TIMEOUT} s")

        # Build valid ID sets from controller for validation
        valid_valve_ids = {int(valve["id"]) for valve in controller.valve_info}
        valid_sensor_ids = {int(sensor["id"]) for sensor in controller.pressure_sensor_info}
        
        sensor_pressure_ranges = {}
        for sensor in controller.pressure_sensor_info:
            sensor_id = int(sensor["id"])
            if "min_pressure" in sensor and "max_pressure" in sensor:
                sensor_pressure_ranges[sensor_id] = {
                    "min": float(sensor["min_pressure"]),
                    "max": float(sensor["max_pressure"])
                }

        def validate_action(action: dict, action_path: str, in_grouped_action: bool = False) -> Optional[int]:
            """Helper function to validate a single action"""
            if not isinstance(action, dict):
                raise ValueError(f"{action_path} must be a dict, got: {type(action).__name__}")
            
            if "type" not in action:
                raise KeyError(f"{action_path} missing required key: 'type'")
            
            action_type = action["type"]
            if not isinstance(action_type, str):
                raise ValueError(f"{action_path}['type'] must be a string, got: {type(action_type).__name__}")
            
            valid_action_types = ("set_valve", "pulse_valve", "wait")
            if action_type not in valid_action_types:
                raise ValueError(f"{action_path}['type'] has invalid value '{action_type}', must be one of: {valid_action_types}")
            
            if action_type == "set_valve":
                if "valve_id" not in action:
                    raise KeyError(f"{action_path} missing required key: 'valve_id'")
                if "state" not in action:
                    raise KeyError(f"{action_path} missing required key: 'state'")
                
                try:
                    valve_id = int(action["valve_id"])
                except (ValueError, TypeError):
                    raise ValueError(f"{action_path}['valve_id'] must be an integer, got: {type(action['valve_id']).__name__}")
                
                if valve_id not in valid_valve_ids:
                    raise ValueError(f"{action_path}['valve_id'] references unknown valve ID: {valve_id}")
                
                state = action["state"]
                if not isinstance(state, str):
                    raise ValueError(f"{action_path}['state'] must be a string, got: {type(state).__name__}")
                if state.lower() not in ("open", "closed"):
                    raise ValueError(f"{action_path}['state'] has invalid value '{state}', must be 'open' or 'closed'")
                
                return valve_id
            
            elif action_type == "pulse_valve":
                if "valve_id" not in action:
                    raise KeyError(f"{action_path} missing required key: 'valve_id'")
                if "duration" not in action:
                    raise KeyError(f"{action_path} missing required key: 'duration'")
                
                try:
                    valve_id = int(action["valve_id"])
                except (ValueError, TypeError):
                    raise ValueError(f"{action_path}['valve_id'] must be an integer, got: {type(action['valve_id']).__name__}")
                
                if valve_id not in valid_valve_ids:
                    raise ValueError(f"{action_path}['valve_id'] references unknown valve ID: {valve_id}")
                
                try:
                    duration = float(action["duration"])
                except (ValueError, TypeError):
                    raise ValueError(f"{action_path}['duration'] must be a number, got: {type(action['duration']).__name__}")
                
                if duration <= 0:
                    raise ValueError(f"{action_path}['duration'] must be positive, got: {duration}")
                
                return valve_id
            
            elif action_type == "wait":
                if in_grouped_action:
                    raise ValueError(f"{action_path} has type 'wait' which is not allowed in grouped actions")
                
                if "duration" not in action:
                    raise KeyError(f"{action_path} missing required key: 'duration'")
                
                try:
                    duration = float(action["duration"])
                except (ValueError, TypeError):
                    raise ValueError(f"{action_path}['duration'] must be a number, got: {type(action['duration']).__name__}")
                
                if duration <= 0:
                    raise ValueError(f"{action_path}['duration'] must be positive, got: {duration}")
                
                return None
            
            return None
        
        def validate_requirement(requirement: dict, req_path: str) -> None:
            """Helper function to validate a single requirement"""
            if not isinstance(requirement, dict):
                raise ValueError(f"{req_path} must be a dict, got: {type(requirement).__name__}")
            
            if "type" not in requirement:
                raise KeyError(f"{req_path} missing required key: 'type'")
            
            req_type = requirement["type"]
            if not isinstance(req_type, str):
                raise ValueError(f"{req_path}['type'] must be a string, got: {type(req_type).__name__}")
            
            valid_req_types = ("pressure_below", "pressure_above", "pressure_between", "valve_state", "custom_message")
            if req_type not in valid_req_types:
                raise ValueError(f"{req_path}['type'] has invalid value '{req_type}', must be one of: {valid_req_types}")
            
            if req_type == "pressure_below":
                if "sensor_id" not in requirement:
                    raise KeyError(f"{req_path} missing required key: 'sensor_id'")
                if "threshold" not in requirement:
                    raise KeyError(f"{req_path} missing required key: 'threshold'")
                
                try:
                    sensor_id = int(requirement["sensor_id"])
                except (ValueError, TypeError):
                    raise ValueError(f"{req_path}['sensor_id'] must be an integer, got: {type(requirement['sensor_id']).__name__}")
                
                if sensor_id not in valid_sensor_ids:
                    raise ValueError(f"{req_path}['sensor_id'] references unknown sensor ID: {sensor_id}")
                
                try:
                    threshold = float(requirement["threshold"])
                except (ValueError, TypeError):
                    raise ValueError(f"{req_path}['threshold'] must be a number, got: {type(requirement['threshold']).__name__}")
                
                if sensor_id in sensor_pressure_ranges:
                    pressure_range = sensor_pressure_ranges[sensor_id]
                    if threshold < pressure_range["min"] or threshold > pressure_range["max"]:
                        raise ValueError(f"{req_path}['threshold'] value {threshold} is outside sensor {sensor_id} range [{pressure_range['min']}, {pressure_range['max']}]")
            
            elif req_type == "pressure_above":
                if "sensor_id" not in requirement:
                    raise KeyError(f"{req_path} missing required key: 'sensor_id'")
                if "threshold" not in requirement:
                    raise KeyError(f"{req_path} missing required key: 'threshold'")
                
                try:
                    sensor_id = int(requirement["sensor_id"])
                except (ValueError, TypeError):
                    raise ValueError(f"{req_path}['sensor_id'] must be an integer, got: {type(requirement['sensor_id']).__name__}")
                
                if sensor_id not in valid_sensor_ids:
                    raise ValueError(f"{req_path}['sensor_id'] references unknown sensor ID: {sensor_id}")
                
                try:
                    threshold = float(requirement["threshold"])
                except (ValueError, TypeError):
                    raise ValueError(f"{req_path}['threshold'] must be a number, got: {type(requirement['threshold']).__name__}")
                
                if sensor_id in sensor_pressure_ranges:
                    pressure_range = sensor_pressure_ranges[sensor_id]
                    if threshold < pressure_range["min"] or threshold > pressure_range["max"]:
                        raise ValueError(f"{req_path}['threshold'] value {threshold} is outside sensor {sensor_id} range [{pressure_range['min']}, {pressure_range['max']}]")
            
            elif req_type == "pressure_between":
                if "sensor_id" not in requirement:
                    raise KeyError(f"{req_path} missing required key: 'sensor_id'")
                if "min_threshold" not in requirement:
                    raise KeyError(f"{req_path} missing required key: 'min_threshold'")
                if "max_threshold" not in requirement:
                    raise KeyError(f"{req_path} missing required key: 'max_threshold'")
                
                try:
                    sensor_id = int(requirement["sensor_id"])
                except (ValueError, TypeError):
                    raise ValueError(f"{req_path}['sensor_id'] must be an integer, got: {type(requirement['sensor_id']).__name__}")
                
                if sensor_id not in valid_sensor_ids:
                    raise ValueError(f"{req_path}['sensor_id'] references unknown sensor ID: {sensor_id}")
                
                try:
                    min_threshold = float(requirement["min_threshold"])
                except (ValueError, TypeError):
                    raise ValueError(f"{req_path}['min_threshold'] must be a number, got: {type(requirement['min_threshold']).__name__}")
                
                try:
                    max_threshold = float(requirement["max_threshold"])
                except (ValueError, TypeError):
                    raise ValueError(f"{req_path}['max_threshold'] must be a number, got: {type(requirement['max_threshold']).__name__}")
                
                if min_threshold >= max_threshold:
                    raise ValueError(f"{req_path} has 'min_threshold' ({min_threshold}) >= 'max_threshold' ({max_threshold})")
                
                if sensor_id in sensor_pressure_ranges:
                    pressure_range = sensor_pressure_ranges[sensor_id]
                    if min_threshold < pressure_range["min"] or min_threshold > pressure_range["max"]:
                        raise ValueError(f"{req_path}['min_threshold'] value {min_threshold} is outside sensor {sensor_id} range [{pressure_range['min']}, {pressure_range['max']}]")
                    if max_threshold < pressure_range["min"] or max_threshold > pressure_range["max"]:
                        raise ValueError(f"{req_path}['max_threshold'] value {max_threshold} is outside sensor {sensor_id} range [{pressure_range['min']}, {pressure_range['max']}]")
            
            elif req_type == "valve_state":
                if "valve_id" not in requirement:
                    raise KeyError(f"{req_path} missing required key: 'valve_id'")
                if "state" not in requirement:
                    raise KeyError(f"{req_path} missing required key: 'state'")
                
                try:
                    valve_id = int(requirement["valve_id"])
                except (ValueError, TypeError):
                    raise ValueError(f"{req_path}['valve_id'] must be an integer, got: {type(requirement['valve_id']).__name__}")
                
                if valve_id not in valid_valve_ids:
                    raise ValueError(f"{req_path}['valve_id'] references unknown valve ID: {valve_id}")
                
                state = requirement["state"]
                if not isinstance(state, str):
                    raise ValueError(f"{req_path}['state'] must be a string, got: {type(state).__name__}")
                if state.lower() not in ("open", "closed"):
                    raise ValueError(f"{req_path}['state'] has invalid value '{state}', must be 'open' or 'closed'")
            
            elif req_type == "custom_message":
                if "message" not in requirement:
                    raise KeyError(f"{req_path} missing required key: 'message'")
                
                message = requirement["message"]
                if not isinstance(message, str):
                    raise ValueError(f"{req_path}['message'] must be a string, got: {type(message).__name__}")
                
                if len(message.strip()) == 0:
                    raise ValueError(f"{req_path}['message'] cannot be empty")

        def validate_actions_list(actions: list, base_path: str) -> None:
            """Helper function to validate a list of actions"""
            if not isinstance(actions, list):
                raise ValueError(f"{base_path} must be a list, got: {type(actions).__name__}")
            
            if len(actions) == 0:
                raise ValueError(f"{base_path} cannot be empty")
            
            for k, action in enumerate(actions):
                action_path = f"{base_path}[{k}]"
                
                if isinstance(action, list):
                    if len(action) == 0:
                        raise ValueError(f"{action_path} grouped action cannot be empty")
                    
                    valve_ids_in_group = []
                    for m, grouped_action in enumerate(action):
                        grouped_path = f"{action_path}[{m}]"
                        valve_id = validate_action(grouped_action, grouped_path, in_grouped_action=True)
                        if valve_id is not None:
                            valve_ids_in_group.append(valve_id)
                    
                    if len(valve_ids_in_group) != len(set(valve_ids_in_group)):
                        raise ValueError(f"{action_path} grouped action contains multiple operations on the same valve")
                else:
                    validate_action(action, action_path, in_grouped_action=False)

        # Validate invalid_valve_states
        if not isinstance(invalid_valve_states, list):
            raise ValueError(f"invalid_valve_states must be a list, got: {type(invalid_valve_states).__name__}")
        
        for i, state_config in enumerate(invalid_valve_states):
            config_path = f"invalid_valve_states[{i}]"
            
            if not isinstance(state_config, dict):
                raise ValueError(f"{config_path} must be a dict, got: {type(state_config).__name__}")
            
            if len(state_config) == 0:
                raise ValueError(f"{config_path} must have at least one state key ('open' or 'closed')")
            
            for state_key, valve_ids in state_config.items():
                if state_key not in ("open", "closed"):
                    raise ValueError(f"{config_path} has invalid state key '{state_key}', must be 'open' or 'closed'")
                
                if not isinstance(valve_ids, list):
                    raise ValueError(f"{config_path}['{state_key}'] must be a list, got: {type(valve_ids).__name__}")
                
                for j, valve_id in enumerate(valve_ids):
                    try:
                        valve_id_int = int(valve_id)
                    except (ValueError, TypeError):
                        raise ValueError(f"{config_path}['{state_key}'][{j}] must be an integer, got: {type(valve_id).__name__}")
                    
                    if valve_id_int not in valid_valve_ids:
                        raise ValueError(f"{config_path}['{state_key}'][{j}] references unknown valve ID: {valve_id_int}")
                
                valve_id_ints = [int(v) for v in valve_ids]
                if len(valve_id_ints) != len(set(valve_id_ints)):
                    raise ValueError(f"{config_path}['{state_key}'] contains duplicate valve IDs")

        # Validate procedures
        if not isinstance(procedures, list):
            raise ValueError(f"procedures must be a list, got: {type(procedures).__name__}")
        
        procedure_names = set()
        for i, procedure in enumerate(procedures):
            proc_path = f"procedures[{i}]"
            
            if not isinstance(procedure, dict):
                raise ValueError(f"{proc_path} must be a dict, got: {type(procedure).__name__}")
            
            if "name" not in procedure:
                raise KeyError(f"{proc_path} missing required key: 'name'")
            if "steps" not in procedure:
                raise KeyError(f"{proc_path} missing required key: 'steps'")
            
            proc_name = procedure["name"]
            if not isinstance(proc_name, str):
                raise ValueError(f"{proc_path}['name'] must be a string, got: {type(proc_name).__name__}")
            if len(proc_name.strip()) == 0:
                raise ValueError(f"{proc_path}['name'] cannot be empty")
            
            if proc_name in procedure_names:
                raise ValueError(f"{proc_path}['name'] is a duplicate: '{proc_name}'")
            procedure_names.add(proc_name)
            
            steps = procedure["steps"]
            if not isinstance(steps, list):
                raise ValueError(f"{proc_path}['steps'] must be a list, got: {type(steps).__name__}")
            
            if len(steps) == 0:
                raise ValueError(f"{proc_path}['steps'] cannot be empty")
            
            step_names = set()
            
            for j, step in enumerate(steps):
                step_path = f"{proc_path}['steps'][{j}]"
                
                if not isinstance(step, dict):
                    raise ValueError(f"{step_path} must be a dict, got: {type(step).__name__}")
                
                if "name" not in step:
                    raise KeyError(f"{step_path} missing required key: 'name'")
                if "actions" not in step:
                    raise KeyError(f"{step_path} missing required key: 'actions'")
                
                step_name = step["name"]
                if not isinstance(step_name, str):
                    raise ValueError(f"{step_path}['name'] must be a string, got: {type(step_name).__name__}")
                if len(step_name.strip()) == 0:
                    raise ValueError(f"{step_path}['name'] cannot be empty")
                
                if step_name in step_names:
                    raise ValueError(f"{step_path}['name'] is a duplicate within procedure '{proc_name}': '{step_name}'")
                step_names.add(step_name)
                
                if "requirements" in step:
                    requirements = step["requirements"]
                    if not isinstance(requirements, list):
                        raise ValueError(f"{step_path}['requirements'] must be a list, got: {type(requirements).__name__}")
                    
                    for k, requirement in enumerate(requirements):
                        req_path = f"{step_path}['requirements'][{k}]"
                        validate_requirement(requirement, req_path)
                
                validate_actions_list(step["actions"], f"{step_path}['actions']")

        # Validate system_safe_states
        if not isinstance(system_safe_states, list):
            raise ValueError(f"system_safe_states must be a list, got: {type(system_safe_states).__name__}")
        
        safe_state_names = set()
        for i, safe_state in enumerate(system_safe_states):
            state_path = f"system_safe_states[{i}]"
            
            if not isinstance(safe_state, dict):
                raise ValueError(f"{state_path} must be a dict, got: {type(safe_state).__name__}")
            
            if "name" not in safe_state:
                raise KeyError(f"{state_path} missing required key: 'name'")
            if "actions" not in safe_state:
                raise KeyError(f"{state_path} missing required key: 'actions'")
            
            state_name = safe_state["name"]
            if not isinstance(state_name, str):
                raise ValueError(f"{state_path}['name'] must be a string, got: {type(state_name).__name__}")
            if len(state_name.strip()) == 0:
                raise ValueError(f"{state_path}['name'] cannot be empty")
            
            if state_name in safe_state_names:
                raise ValueError(f"{state_path}['name'] is a duplicate: '{state_name}'")
            safe_state_names.add(state_name)
            
            # Validate requirements (optional)
            if "requirements" in safe_state:
                requirements = safe_state["requirements"]
                if not isinstance(requirements, list):
                    raise ValueError(f"{state_path}['requirements'] must be a list, got: {type(requirements).__name__}")
                
                for k, requirement in enumerate(requirements):
                    req_path = f"{state_path}['requirements'][{k}]"
                    validate_requirement(requirement, req_path)
            
            validate_actions_list(safe_state["actions"], f"{state_path}['actions']")

        self._controller = controller
        self._logger = logger
        self._safe_state_timeout = safe_state_timeout
        self._system_safe_states = system_safe_states
        self._invalid_valve_states = invalid_valve_states
        self._procedures = procedures
        self._shutdown_flag = False
        self._safe_mode = False
        self._last_user_heartbeat = 0.0
        self._thread_lock = threading.Lock()

        # Procedure execution state
        self._procedure_step_completion: Dict[int, set] = {}  # procedure_index -> set of completed step indices
        self._currently_executing: Optional[Dict] = None  # {"procedure_index": int, "step_index": int, "user": str, "start_time": float}
        self._safing_system: Optional[Dict] = None  # {"user": str, "start_time": float} when system is being safed

        self._logger.log_data(["system", "info", f"Safe state timeout: {self._safe_state_timeout}s"])
        self._logger.log_data(["system", "info", f"System safe states: {self._system_safe_states}"])
        self._logger.log_data(["system", "info", f"Invalid valve states: {self._invalid_valve_states}"])

        monitor_thread = threading.Thread(target = self._monitor_safe_mode, daemon = True)
        monitor_thread.start()

    @classmethod
    def from_config(cls, controller: Controller, config: Dict) -> "ControllerOperations":
        """
        Initializes a ControllerOperations object from a configuration dictionary (the website config).

        Args:
            controller: The Controller object to operate.
            config: The target configuration dict.
        """
        if 'general_config' not in config:
            raise KeyError(f"Website config missing key: 'general_config'")
        if 'invalid_valve_states' not in config:
            raise KeyError(f"Website config missing key: 'invalid_valve_states'")
        if 'procedures' not in config:
            raise KeyError(f"Website config missing key: 'procedures'")
        if 'website_log_path' not in config['general_config']:
            raise KeyError(f"Website config missing key: 'general_config.website_log_path'")
        if 'safe_state_timeout' not in config['general_config']:
            raise KeyError(f"Website config missing key: 'general_config.safe_state_timeout'")
        if 'system_safe_states' not in config:
            raise KeyError(f"Website config missing key: 'system_safe_states'")

        website_log_path = config['general_config']['website_log_path']
        if not isinstance(website_log_path, str):
            raise ValueError(f"Website config 'general_config.website_log_path' must be a string, got: {type(website_log_path).__name__}")

        invalid_valve_states = config['invalid_valve_states']
        if not isinstance(invalid_valve_states, list):
            raise ValueError(f"Website config 'invalid_valve_states' must be a list, got: {type(invalid_valve_states).__name__}")

        procedures = config['procedures']
        if not isinstance(procedures, list):
            raise ValueError(f"Website config 'procedures' must be a list, got: {type(procedures).__name__}")

        try:
            safe_state_timeout = float(config['general_config']['safe_state_timeout'])
        except (ValueError, TypeError):
            raise ValueError(f"Website config 'general_config.safe_state_timeout' must be a number, got: {type(config['general_config']['safe_state_timeout']).__name__}")

        system_safe_states = config['system_safe_states']
        if not isinstance(system_safe_states, list):
            raise ValueError(f"Website config 'system_safe_states' must be a list, got: {type(system_safe_states).__name__}")

        return cls(
            controller = controller,
            safe_state_timeout = safe_state_timeout,
            system_safe_states = system_safe_states,
            invalid_valve_states = invalid_valve_states,
            procedures = procedures,
            logger = Logger(path = website_log_path, col = ["user", "type", "status"])
        )

    def __del__(self) -> None:
        self.shutdown()

    def shutdown(self) -> None:
        """
        Shuts down operations: stops the safe mode monitor and aborts running action sequences at the next action.
        After this is called, other methods raise OperationsShutdownError. Calling it again does nothing.
        """
        with self._thread_lock:
            self._shutdown_flag = True

    def _check_not_shutdown(self) -> None:
        """
        Raises OperationsShutdownError if shut down. Call with the lock held.
        """
        if self._shutdown_flag:
            raise OperationsShutdownError()

    def _check_procedure_index(self, procedure_index: int) -> Dict:
        """
        Returns the procedure at the given index or raises ValueError.
        """
        if procedure_index < 0 or procedure_index >= len(self._procedures):
            raise ValueError(f"Invalid procedure index: {procedure_index}")
        return self._procedures[procedure_index]

    def _check_step_index(self, procedure_index: int, step_index: int) -> Dict:
        """
        Returns the step at the given indices or raises ValueError.
        """
        procedure = self._check_procedure_index(procedure_index)
        if step_index < 0 or step_index >= len(procedure["steps"]):
            raise ValueError(f"Invalid step index: {step_index}")
        return procedure["steps"][step_index]

    def _check_valves_modifiable_locked(self) -> None:
        """
        Raises BusyError if valves cannot be modified right now. Call with the lock held.
        """
        if self._currently_executing is not None:
            exec_user = self._currently_executing["user"]
            raise BusyError(f"Cannot modify valves while step is executing (by {exec_user})")
        if self._safing_system is not None:
            safing_user = self._safing_system["user"]
            raise BusyError(f"Cannot modify valves while system is being safed (by {safing_user})")

    ###############################################################################################
    # Queries
    ###############################################################################################

    @property
    def logger(self) -> Logger:
        """
        Logger used for operation status/action/error logging (columns: user, type, status).
        """
        return self._logger

    @property
    def procedures(self) -> List[dict]:
        """
        Configured procedures.
        """
        return self._procedures

    @property
    def invalid_valve_states(self) -> List[dict]:
        """
        Configured invalid valve states.
        """
        return self._invalid_valve_states

    @property
    def system_safe_states(self) -> List[dict]:
        """
        Configured system safe states.
        """
        return self._system_safe_states

    @property
    def safe_state_timeout(self) -> float:
        """
        Safe state timeout in seconds.
        """
        return self._safe_state_timeout

    def get_valve_info(self) -> List[dict]:
        """
        Gets info for all valves (id, name, default_state, current_state, is_pulsing, and pulse_duration /
        pulse_elapsed / pulse_remaining while pulsing).
        """
        with self._thread_lock:
            self._check_not_shutdown()
            current_time = time.time()
            valve_info = self._controller.valve_info
            for valve in valve_info:
                pulse_info = self._controller.get_pulse_info(valve["id"])
                valve["is_pulsing"] = pulse_info is not None
                if pulse_info:
                    elapsed = current_time - pulse_info["start_time"]
                    valve["pulse_duration"] = pulse_info["duration"]
                    valve["pulse_elapsed"] = elapsed
                    valve["pulse_remaining"] = max(0, pulse_info["duration"] - elapsed)
            return valve_info

    def get_sensor_info(self) -> List[dict]:
        """
        Gets info for all pressure sensors (id, name, current_pressure, min_pressure, max_pressure).
        """
        with self._thread_lock:
            self._check_not_shutdown()
            return self._controller.pressure_sensor_info

    def get_safe_mode(self) -> bool:
        """
        Gets whether safe mode is enabled.
        """
        with self._thread_lock:
            self._check_not_shutdown()
            return self._safe_mode

    def get_procedure_status(self) -> Dict:
        """
        Gets step completion for all procedures and the currently executing step.
        Returns: {"completion": {"<procedure_index>": [step indices]}, "executing": {"procedure_index", "step_index", "user"} or None}
        """
        with self._thread_lock:
            self._check_not_shutdown()
            completion = {str(k): list(v) for k, v in self._procedure_step_completion.items()}
            executing = None
            if self._currently_executing:
                executing = {
                    "procedure_index": self._currently_executing["procedure_index"],
                    "step_index": self._currently_executing["step_index"],
                    "user": self._currently_executing["user"]
                }
            return {
                "completion": completion,
                "executing": executing
            }

    def get_safing_status(self) -> Dict:
        """
        Gets whether the system is currently being safed. Returns: {"safing": bool, "user": str or None}
        """
        with self._thread_lock:
            self._check_not_shutdown()
            if self._safing_system:
                return {"safing": True, "user": self._safing_system["user"]}
            return {"safing": False, "user": None}

    def get_status(self) -> Dict:
        """
        Gets a snapshot of live state: valves, sensors, safe mode, safing and procedure status.
        """
        return {
            "valves": self.get_valve_info(),
            "sensors": self.get_sensor_info(),
            "safe_mode": self.get_safe_mode(),
            "safing": self.get_safing_status(),
            "procedure_status": self.get_procedure_status(),
        }

    def get_config(self) -> Dict:
        """
        Gets static configuration: valve and sensor names/ranges, procedures, invalid valve states and safe states.
        """
        valves = [{k: v[k] for k in ("id", "name", "default_state")} for v in self.get_valve_info()]
        sensors = [{k: s[k] for k in ("id", "name", "min_pressure", "max_pressure")} for s in self.get_sensor_info()]
        return {
            "valves": valves,
            "sensors": sensors,
            "procedures": self._procedures,
            "invalid_valve_states": self._invalid_valve_states,
            "system_safe_states": self._system_safe_states,
            "safe_state_timeout": self._safe_state_timeout,
        }

    ###############################################################################################
    # Commands
    ###############################################################################################

    def check_valves_modifiable(self) -> None:
        """
        Raises BusyError if valves cannot be modified right now (a step is executing or the system is being safed).
        """
        with self._thread_lock:
            self._check_not_shutdown()
            self._check_valves_modifiable_locked()

    def set_valve_states(self, changes: Dict[str, object], user: str) -> None:
        """
        Applies valve changes. Applies every change it can, then raises ValveChangeError listing the ones that failed.

        Args:
            changes: Dict of valve id -> action, where action is "open", "closed" or "pulse:<duration>".
                     Ids may be strings or ints; failures are reported under the id as given.
            user: Who requested the change (for logging).
        """
        with self._thread_lock:
            self._check_not_shutdown()
            self._check_valves_modifiable_locked()

            if len(changes) == 0:
                return

            failed_valves: Dict[str, str] = {}
            for valve_id_str, action in changes.items():
                try:
                    try:
                        valve_id = int(valve_id_str)
                    except (ValueError, TypeError):
                        if settings.PRINT_WEBSITE_ERRORS:
                            print(f"WEBSITE ERROR: Invalid valve ID from {user}: {valve_id_str}")
                        error_msg = f"Invalid valve ID: {valve_id_str}"
                        failed_valves[valve_id_str] = error_msg
                        self._logger.log_data([user, "error", error_msg])
                        continue

                    if not isinstance(action, str):
                        if settings.PRINT_WEBSITE_ERRORS:
                            print(f"WEBSITE ERROR: Action for valve {valve_id} from {user} must be a string")
                        error_msg = f"Action for valve {valve_id} must be a string"
                        failed_valves[valve_id_str] = error_msg
                        self._logger.log_data([user, "error", error_msg])
                        continue

                    # Check if valve is currently pulsing
                    if self._controller.get_pulse_info(valve_id) is not None:
                        if settings.PRINT_WEBSITE_ERRORS:
                            print(f"WEBSITE ERROR: Valve {valve_id} is currently pulsing, cannot modify")
                        error_msg = f"Valve {valve_id} is currently pulsing"
                        failed_valves[valve_id_str] = error_msg
                        self._logger.log_data([user, "error", error_msg])
                        continue

                    action = action.strip()

                    # Check if this is a pulse command (format: "pulse:duration")
                    if action.lower().startswith("pulse:"):
                        try:
                            duration = float(action[6:])
                        except (ValueError, TypeError):
                            if settings.PRINT_WEBSITE_ERRORS:
                                print(f"WEBSITE ERROR: Invalid pulse duration for valve {valve_id} from {user}: {action}")
                            error_msg = f"Invalid pulse duration: {action}"
                            failed_valves[valve_id_str] = error_msg
                            self._logger.log_data([user, "error", error_msg])
                            continue

                        self._controller.pulse_valve(id=valve_id, duration=duration)
                        if settings.PRINT_WEBSITE_STATUS:
                            print(f"WEBSITE STATUS: User {user} pulsed valve {valve_id} for {duration}s")
                        self._logger.log_data([user, "action", f"Pulsed valve {valve_id} for {duration}s"])
                    else:
                        # Regular state change (open/closed)
                        try:
                            state_enum = ValveState[action.upper()]
                        except (KeyError, AttributeError):
                            if settings.PRINT_WEBSITE_ERRORS:
                                print(f"WEBSITE ERROR: Invalid valve action from {user} for valve {valve_id}: {action}")
                            error_msg = f"Invalid valve action: {action}"
                            failed_valves[valve_id_str] = error_msg
                            self._logger.log_data([user, "error", error_msg])
                            continue

                        self._controller.set_valve(id=valve_id, state=state_enum)
                        if settings.PRINT_WEBSITE_STATUS:
                            print(f"WEBSITE STATUS: User {user} set valve {valve_id} to {action}")
                        self._logger.log_data([user, "action", f"Set valve {valve_id} to {action}"])

                except ValueError as e:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: Failed to set valve state for {user}: {e}")
                    error_msg = f"Failed to set valve state: {e}"
                    failed_valves[valve_id_str] = error_msg
                    self._logger.log_data([user, "error", error_msg])

                except RuntimeError as e:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: Failed to modify valve {valve_id_str} for {user}: {e}")
                    error_msg = str(e)
                    failed_valves[valve_id_str] = error_msg
                    self._logger.log_data([user, "error", error_msg])

                except Exception as e:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: Failed to set valve {valve_id_str} state for {user}: {e}")
                    error_msg = f"Failed to set valve {valve_id_str} state: {e}"
                    failed_valves[valve_id_str] = error_msg
                    self._logger.log_data([user, "error", error_msg])

            if len(failed_valves) > 0:
                raise ValveChangeError(failed_valves)

    def set_safe_mode(self, enabled: bool, user: str) -> None:
        """
        Enables or disables safe mode. Enabling it starts the safe state timeout countdown.
        """
        if not isinstance(enabled, bool):
            raise ValueError("'safe_mode' field must be a boolean")
        with self._thread_lock:
            self._check_not_shutdown()
            self._safe_mode = enabled
            if enabled:
                self._last_user_heartbeat = time.time()

    def safe_system(self, user: str) -> None:
        """
        Starts a safe system operation in a background thread and returns immediately. Runs the actions of the
        first safe state whose requirements are met. Valve changes and steps are blocked while it runs.
        """
        with self._thread_lock:
            self._check_not_shutdown()
            self._start_safe_system_locked(user)

    def _start_safe_system_locked(self, user: str) -> None:
        """
        Implementation of safe_system. Call with the lock held. Used by both the manual safe system command
        and the safe mode auto-safe timeout. Raises BusyError if already safing or a step is executing.
        """
        # Check if system is already being safed
        if self._safing_system is not None:
            safing_user = self._safing_system["user"]
            raise BusyError(
                f"System is already being safed by {safing_user}",
                {"safing": {"user": safing_user}}
            )

        # Check if a step is executing
        if self._currently_executing is not None:
            exec_user = self._currently_executing["user"]
            exec_step = self._currently_executing["step_index"]
            exec_proc = self._currently_executing["procedure_index"]
            raise BusyError(
                f"Cannot safe system while step is executing (by {exec_user})",
                {"executing": {
                    "procedure_index": exec_proc,
                    "step_index": exec_step,
                    "user": exec_user
                }}
            )

        # Mark system as being safed
        self._safing_system = {
            "user": user,
            "start_time": time.time()
        }

        if settings.PRINT_WEBSITE_STATUS:
            print(f"WEBSITE STATUS: User {user} initiated safe system")
        self._logger.log_data([user, "action", "Initiated safe system"])

        # Inner function to execute safe system in background thread
        def safe_system_thread() -> None:
            # Find the first safe state whose requirements are met
            safe_state_executed = False

            for safe_state in self._system_safe_states:
                state_name = safe_state.get("name", "Unnamed")
                requirements = safe_state.get("requirements", [])

                # Check if all requirements are met
                requirements_met = all(self._check_safe_state_requirement(req) for req in requirements) if requirements else True

                if requirements_met:
                    if settings.PRINT_WEBSITE_STATUS:
                        print(f"WEBSITE STATUS: Executing safe state '{state_name}'")
                    self._logger.log_data([user, "action", f"Executing safe state '{state_name}'"])

                    actions = safe_state.get("actions", [])
                    success = self._execute_actions(actions, user=user)

                    with self._thread_lock:
                        self._safing_system = None

                    if success:
                        if settings.PRINT_WEBSITE_STATUS:
                            print(f"WEBSITE STATUS: Safe state '{state_name}' completed successfully")
                        self._logger.log_data([user, "action", f"Safe state '{state_name}' completed"])
                    else:
                        if settings.PRINT_WEBSITE_ERRORS:
                            print(f"WEBSITE ERROR: Safe state '{state_name}' execution failed")
                        self._logger.log_data([user, "error", f"Safe state '{state_name}' execution failed"])

                    safe_state_executed = True
                    break

            if not safe_state_executed:
                with self._thread_lock:
                    self._safing_system = None
                if settings.PRINT_WEBSITE_STATUS:
                    print(f"WEBSITE STATUS: No safe state requirements met, no action taken")
                self._logger.log_data([user, "status", "No safe state requirements met"])

        # Start safe system execution in background thread
        thread = threading.Thread(target=safe_system_thread, daemon=True)
        thread.start()

    def start_step(self, procedure_index: int, step_index: int, user: str) -> None:
        """
        Starts executing a step's actions in a background thread and returns immediately.
        Only one step can execute at a time, and not while the system is being safed.
        """
        with self._thread_lock:
            self._check_not_shutdown()
            step = self._check_step_index(procedure_index, step_index)

            # Check if system is being safed
            if self._safing_system is not None:
                safing_user = self._safing_system["user"]
                if settings.PRINT_WEBSITE_ERRORS:
                    print(f"WEBSITE ERROR: User {user} attempted to start step execution while system is being safed by {safing_user}")
                self._logger.log_data([user, "error", f"Cannot start step: system being safed by {safing_user}"])
                raise BusyError(
                    f"Cannot execute step while system is being safed (by {safing_user})",
                    {"safing": {"user": safing_user}}
                )

            # Check if another step is already executing
            if self._currently_executing is not None:
                exec_proc = self._currently_executing["procedure_index"]
                exec_step = self._currently_executing["step_index"]
                exec_user = self._currently_executing["user"]
                if settings.PRINT_WEBSITE_ERRORS:
                    print(f"WEBSITE ERROR: User {user} attempted to start step execution while step {exec_step} in procedure {exec_proc} is already executing by {exec_user}")
                self._logger.log_data([user, "error", f"Step already executing: procedure {exec_proc}, step {exec_step} by {exec_user}"])
                raise BusyError(
                    "Another step is already being executed",
                    {"executing": {
                        "procedure_index": exec_proc,
                        "step_index": exec_step,
                        "user": exec_user
                    }}
                )

            # Mark step as executing
            self._currently_executing = {
                "procedure_index": procedure_index,
                "step_index": step_index,
                "user": user,
                "start_time": time.time()
            }

            step_name = step["name"]
            if settings.PRINT_WEBSITE_STATUS:
                print(f"WEBSITE STATUS: User {user} started executing step '{step_name}' (procedure {procedure_index}, step {step_index})")
            self._logger.log_data([user, "action", f"Started executing step '{step_name}' (procedure {procedure_index}, step {step_index})"])

            # Inner function to execute step in background thread
            def execute_step_thread() -> None:
                actions = step.get("actions", [])
                success = self._execute_actions(actions, user=user)

                # Mark step complete and clear executing state
                with self._thread_lock:
                    self._currently_executing = None
                    if success:
                        if procedure_index not in self._procedure_step_completion:
                            self._procedure_step_completion[procedure_index] = set()
                        self._procedure_step_completion[procedure_index].add(step_index)
                        if settings.PRINT_WEBSITE_STATUS:
                            print(f"WEBSITE STATUS: Step '{step_name}' completed successfully (procedure {procedure_index}, step {step_index})")
                        self._logger.log_data([user, "action", f"Step '{step_name}' completed (procedure {procedure_index}, step {step_index})"])
                    else:
                        if settings.PRINT_WEBSITE_STATUS:
                            print(f"WEBSITE STATUS: Step '{step_name}' execution ended without completion (procedure {procedure_index}, step {step_index})")
                        self._logger.log_data([user, "action", f"Step '{step_name}' ended without completion (procedure {procedure_index}, step {step_index})"])

            # Start execution in background thread
            exec_thread = threading.Thread(
                target=execute_step_thread,
                daemon=True
            )
            exec_thread.start()

    def set_step_completion(self, procedure_index: int, step_index: int, completed: bool, user: str) -> None:
        """
        Manually sets a step's completion status without executing it.
        """
        if not isinstance(completed, bool):
            raise ValueError("'completed' must be a boolean")
        with self._thread_lock:
            self._check_not_shutdown()
            step = self._check_step_index(procedure_index, step_index)

            # Update completion status
            if procedure_index not in self._procedure_step_completion:
                self._procedure_step_completion[procedure_index] = set()

            if completed:
                self._procedure_step_completion[procedure_index].add(step_index)
            else:
                self._procedure_step_completion[procedure_index].discard(step_index)

            step_name = step["name"]
            if settings.PRINT_WEBSITE_STATUS:
                status_msg = "completed" if completed else "incomplete"
                print(f"WEBSITE STATUS: User {user} marked step '{step_name}' as {status_msg} (procedure {procedure_index}, step {step_index})")
            self._logger.log_data([user, "action", f"Marked step '{step_name}' as {'completed' if completed else 'incomplete'} (procedure {procedure_index}, step {step_index})"])

    def reset_procedure(self, procedure_index: int, user: str) -> None:
        """
        Clears all step completion statuses for a procedure. Rejected while one of its steps is executing.
        """
        with self._thread_lock:
            self._check_not_shutdown()
            procedure = self._check_procedure_index(procedure_index)

            # Check if any step in this procedure is currently executing
            if self._currently_executing is not None and self._currently_executing["procedure_index"] == procedure_index:
                raise BusyError("Cannot reset procedure while a step is executing")

            # Clear completion status for this procedure
            if procedure_index in self._procedure_step_completion:
                del self._procedure_step_completion[procedure_index]

            procedure_name = procedure["name"]
            if settings.PRINT_WEBSITE_STATUS:
                print(f"WEBSITE STATUS: User {user} reset procedure '{procedure_name}' (index {procedure_index})")
            self._logger.log_data([user, "action", f"Reset procedure '{procedure_name}' (index {procedure_index})"])
