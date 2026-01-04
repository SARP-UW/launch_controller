import time
import threading
import os
import logging
from typing import Dict, List, Optional
from flask import Flask, render_template, request, jsonify
from .controller import Controller
from .valve import ValveState
from .logger import Logger
from . import settings
 
# Minimum permissable heartbeat timeout in seconds
MIN_HEARTBEAT_TIMEOUT = 0.1

# Maximum permissable heartbeat timeout in seconds
MAX_HEARTBEAT_TIMEOUT = 1000.0

# Minimum permissable polling rate in Hz
MIN_POLLING_RATE = 0.1

# Maximum permissable polling rate in Hz
MAX_POLLING_RATE = 1000.0

# Minimum permissable safe state timeout in seconds
MIN_SAFE_STATE_TIMEOUT = 0.1

# Maximum permissable safe state timeout in seconds
MAX_SAFE_STATE_TIMEOUT = 1000.0

# Minimum permissable port value
MIN_PORT_VALUE = 1

# Maximum permissable port value
MAX_PORT_VALUE = 65535

# Absolute path to website directory
_WEBSITE_TOP_DIR_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "website")

# Absolute path to website template folder
WEBSITE_TEMPLATE_FOLDER_PATH = os.path.join(_WEBSITE_TOP_DIR_PATH, "templates")

# Absolute path to website static folder
WEBSITE_STATIC_FOLDER_PATH = os.path.join(_WEBSITE_TOP_DIR_PATH, "static")
 
class ControllerWebsite:
    """
    Class which represents the web interface for the controller.
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
    
    def _update_website(self) -> None:
        """
        Background thread method to periodically check user heartbeats and manage safe states.
        """
        interval = 1.0 / self._polling_rate
        while True:
            with self._thread_lock:
                if self._shutdown_flag:
                    break
                try:
                    current_time = time.time()
                    for user, last_heartbeat in dict(self._user_heartbeats).items():
                        if (current_time - last_heartbeat) > self._heartbeat_timeout:
                            if settings.PRINT_WEBSITE_STATUS:
                                print(f"WEBSITE STATUS: User {user} disconnected.")
                            self._website_logger.log_data([user, "status", "User disconnected"])
                            del self._user_heartbeats[user]
                    if self._safe_mode:
                        if (current_time - self._last_user_heartbeat) > self._safe_state_timeout:
                            if settings.PRINT_WEBSITE_STATUS:
                                print(f"WEBSITE STATUS: Safe mode timeout reached, executing safe state.")
                            self._website_logger.log_data(["system", "status", "Safing system"])
                            
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
                                    self._website_logger.log_data(["system", "action", f"Executing safe state '{state_name}'"])
                                    
                                    actions = safe_state.get("actions", [])
                                    success = self._execute_actions(actions, user="system")
                                    
                                    if success:
                                        if settings.PRINT_WEBSITE_STATUS:
                                            print(f"WEBSITE STATUS: Safe state '{state_name}' completed successfully")
                                        self._website_logger.log_data(["system", "action", f"Safe state '{state_name}' completed"])
                                    else:
                                        if settings.PRINT_WEBSITE_ERRORS:
                                            print(f"WEBSITE ERROR: Safe state '{state_name}' execution failed")
                                        self._website_logger.log_data(["system", "error", f"Safe state '{state_name}' execution failed"])
                                    
                                    safe_state_executed = True
                                    break
                            
                            if not safe_state_executed:
                                if settings.PRINT_WEBSITE_STATUS:
                                    print(f"WEBSITE STATUS: No safe state requirements met, no action taken")
                                self._website_logger.log_data(["system", "status", "No safe state requirements met"])
                            
                            self._safe_mode = False
                except Exception as e:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: Update website error: {e}")
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
                self._website_logger.log_data([user, "action", f"Set valve {valve_id} to {state_str}"])
                
            elif action_type == "pulse_valve":
                valve_id = action.get("valve_id")
                duration = float(action.get("duration", 1.0))
                self._controller.pulse_valve(valve_id, duration)
                if settings.PRINT_WEBSITE_STATUS:
                    print(f"WEBSITE STATUS: {user} executed pulse_valve: valve {valve_id} for {duration}s")
                self._website_logger.log_data([user, "action", f"Pulsed valve {valve_id} for {duration}s"])
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
                    self._website_logger.log_data([user, "action", f"Set valve {valve_id} to {state_str} (multi)"])
                    
                elif action_type == "pulse_valve":
                    valve_id = action.get("valve_id")
                    duration = float(action.get("duration", 1.0))
                    self._controller.pulse_valve(valve_id, duration)
                    if settings.PRINT_WEBSITE_STATUS:
                        print(f"WEBSITE STATUS: {user} executed pulse_valve (multi): valve {valve_id} for {duration}s")
                    self._website_logger.log_data([user, "action", f"Pulsed valve {valve_id} for {duration}s (multi)"])
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
            self._website_logger.log_data([user, "error", f"Action execution failed: {e}"])
            return False

    def __init__(self, controller: Controller, port: int, polling_rate: float, heartbeat_timeout: float, safe_state_timeout: float, website_log_path: str, website_title: str, system_safe_states: List[dict], invalid_valve_states: dict, procedures: dict) -> None:
        """
        Initializes a ControllerWebsite object.
        
        Args:
            controller: The Controller object to interface with.
            port: The port number for the web server.
            polling_rate: The rate (in Hz) at which the website polls for data.
            heartbeat_timeout: The time (in seconds) after which a user is considered disconnected if no heartbeat is received.
            website_log_path: Path to file to use for logging website status.
            safe_state_timeout: The time (in seconds) after which the system is put into a safe state if no heartbeat is received from user with safe mode enabled.
            website_title: The title to display in the website header.
            system_safe_states: List of dicts defining safe states with requirements and actions.
            invalid_valve_states: A dict defining invalid valve states.
            procedures: A dict defining procedures that can be executed via the website.
        """
        if controller is None:
            raise ValueError("Invalid controller object")
        if port < MIN_PORT_VALUE:
            raise ValueError(f"Port number is invalid: {port} < {MIN_PORT_VALUE}")
        if port > MAX_PORT_VALUE:
            raise ValueError(f"Port number is invalid: {port} > {MAX_PORT_VALUE}")
        if heartbeat_timeout < MIN_HEARTBEAT_TIMEOUT:
            raise ValueError(f"Heartbeat timeout is invalid: {heartbeat_timeout} < {MIN_HEARTBEAT_TIMEOUT}")
        if heartbeat_timeout > MAX_HEARTBEAT_TIMEOUT:
            raise ValueError(f"Heartbeat timeout is invalid: {heartbeat_timeout} > {MAX_HEARTBEAT_TIMEOUT}")
        if polling_rate < MIN_POLLING_RATE:
            raise ValueError(f"Polling rate is invalid: {polling_rate} < {MIN_POLLING_RATE}")
        if polling_rate > MAX_POLLING_RATE:
            raise ValueError(f"Polling rate is invalid: {polling_rate} > {MAX_POLLING_RATE}")
        if (1 / polling_rate) > heartbeat_timeout:
            raise ValueError(f"Polling period is greater than heartbeat timeout: {1 / polling_rate}s > {heartbeat_timeout}s")
        if safe_state_timeout < MIN_SAFE_STATE_TIMEOUT:
            raise ValueError(f"Safe state timeout is invalid: {safe_state_timeout} < {MIN_SAFE_STATE_TIMEOUT}")
        if safe_state_timeout > MAX_SAFE_STATE_TIMEOUT:
            raise ValueError(f"Safe state timeout is invalid: {safe_state_timeout} > {MAX_SAFE_STATE_TIMEOUT}")
        if safe_state_timeout < heartbeat_timeout:
            raise ValueError(f"Safe state timeout is less than heartbeat timeout: {safe_state_timeout} s < {heartbeat_timeout} s")            

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
        self._port = port
        self._polling_rate = polling_rate
        self._heartbeat_timeout = heartbeat_timeout
        self._website_logger = Logger(
            path = website_log_path,
            col = ["user", "type", "status"]
        )
        self._safe_state_timeout = safe_state_timeout
        self._website_title = website_title
        self._system_safe_states = system_safe_states
        self._invalid_valve_states = invalid_valve_states
        self._procedures = procedures
        self._shutdown_flag = False
        self._safe_mode = False
        self._last_user_heartbeat = 0.0
        self._thread_lock = threading.Lock()
        self._user_heartbeats: Dict[str, float] = {}
        
        # Procedure execution state (server-side tracking)
        self._procedure_step_completion: Dict[int, set] = {}  # procedure_index -> set of completed step indices
        self._currently_executing: Optional[Dict] = None  # {"procedure_index": int, "step_index": int, "user": str, "start_time": float}
        self._safing_system: Optional[Dict] = None  # {"user": str, "start_time": float} when system is being safed
        
        self._app = Flask(
            __name__,
            template_folder = WEBSITE_TEMPLATE_FOLDER_PATH,
            static_folder = WEBSITE_STATIC_FOLDER_PATH
        )

        @self._app.get("/api/get_server_status")
        def get_server_status():
            """
            Gets current server status (running/shutdown).
            """
            if self._shutdown_flag:
                return jsonify({"status": "shutdown"})
            else:
                return jsonify({"status": "running"})

        @self._app.get("/api/send_heartbeat")
        def send_heartbeat():
            """
            Heartbeat endpoint to keep track of connected users.
            """
            user = request.remote_addr
            with self._thread_lock:
                if self._shutdown_flag:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: User attempted to send heartbeat while website shut down.")
                    self._website_logger.log_data([user, "error", "Attempted to send heartbeat while website shut down."])
                    return jsonify({"status": "error", "message": "Website has been shut down"}), 500
                try:
                    if user not in self._user_heartbeats:
                        if settings.PRINT_WEBSITE_STATUS:
                            print(f"WEBSITE STATUS: User {user} connected.")
                        self._website_logger.log_data([user, "status", "User connected"])
                    self._user_heartbeats[user] = time.time()
                    return jsonify({"status": "success"})
                except Exception as e:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: Failed to process heartbeat from {user}: {e}")
                    self._website_logger.log_data([user, "error", f"Failed to process heartbeat: {e}"])
                    return jsonify({"status": "error", "message": "Failed to process heartbeat"}), 500

        @self._app.get("/api/get_valve_info")
        def get_valve_info():
            """
            Gets list of info for all valves (id, name, default_state, current_state).
            """
            user = request.remote_addr
            with self._thread_lock:
                if self._shutdown_flag:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: User attempted to get valve info while website shut down.")
                    self._website_logger.log_data([user, "error", "Attempted to get valve info while website shut down."])
                    return jsonify({"status": "error", "message": "Website has been shut down"}), 503
                try:
                    return jsonify(self._controller.valve_info)
                except Exception as e:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: Failed to get valve info from {user}: {e}")
                    self._website_logger.log_data([user, "error", f"Failed to get valve info: {e}"])
                    return jsonify({"status": "error", "message": "Failed to get valve info"}), 500

        @self._app.get("/api/get_sensor_info")
        def get_sensor_info():
            """
            Gets list of info for all pressure sensors (id, name, current_pressure)
            """
            user = request.remote_addr
            with self._thread_lock:
                if self._shutdown_flag:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: User attempted to get sensor info while website shut down.")
                    self._website_logger.log_data([user, "error", "Attempted to get sensor info while website shut down."])
                    return jsonify({"status": "error", "message": "Website has been shut down"}), 503
                try:
                    return jsonify(self._controller.pressure_sensor_info)
                except Exception as e:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: Failed to get sensor info from {user}: {e}")
                    self._website_logger.log_data([user, "error", f"Failed to get sensor info: {e}"])
                    return jsonify({"status": "error", "message": "Failed to get sensor info"}), 500

        @self._app.post("/api/set_valve_states")
        def set_valve_states():
            """
            Updates valve states based on provided dict (valve_id: state)
            """
            user = request.remote_addr
            with self._thread_lock:
                if self._shutdown_flag:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: User attempted to set valve states while website shut down.")
                    self._website_logger.log_data([user, "error", "Attempted to set valve states while website shut down."])
                    return jsonify({"status": "error", "message": "Website has been shut down"}), 503
                
                # Block valve operations while executing or safing
                if self._currently_executing is not None:
                    exec_user = self._currently_executing["user"]
                    return jsonify({"status": "error", "message": f"Cannot modify valves while step is executing (by {exec_user})"}), 409
                
                if self._safing_system is not None:
                    safing_user = self._safing_system["user"]
                    return jsonify({"status": "error", "message": f"Cannot modify valves while system is being safed (by {safing_user})"}), 409
                
                if not request.is_json:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: Set valve states request from {user} missing JSON body")
                    self._website_logger.log_data([user, "error", "Set valve states request missing JSON body"])
                    return jsonify({"status": "error", "message": "Set valve states request missing JSON body"}), 400

                data = request.get_json()
                if not isinstance(data, dict):
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: Set valve states request from {user} body must be a dict")
                    self._website_logger.log_data([user, "error", "Set valve states request body must be a dict"])
                    return jsonify({"status": "error", "message": "Request body must be a dict"}), 400
            
                if len(data) == 0:
                    return jsonify({"status": "success"})

                failed_valves: Dict[str, str] = {}
                for valve_id_str, state_str in data.items():
                    try:
                        try:
                            valve_id = int(valve_id_str)
                        except (ValueError, TypeError):
                            if settings.PRINT_WEBSITE_ERRORS:
                                print(f"WEBSITE ERROR: Invalid valve ID from {user}: {valve_id_str}")
                            error_msg = f"Invalid valve ID: {valve_id_str}"
                            failed_valves[valve_id_str] = error_msg
                            self._website_logger.log_data([user, "error", error_msg])
                            continue
                        
                        if not isinstance(state_str, str):
                            if settings.PRINT_WEBSITE_ERRORS:
                                print(f"WEBSITE ERROR: State for valve {valve_id} from {user} must be a string")
                            error_msg = f"State for valve {valve_id} must be a string"
                            failed_valves[valve_id_str] = error_msg
                            self._website_logger.log_data([user, "error", error_msg])
                            continue
                        
                        try:
                            state_enum = ValveState[state_str.strip().upper()]
                        except (KeyError, AttributeError):
                            if settings.PRINT_WEBSITE_ERRORS:
                                print(f"WEBSITE ERROR: Invalid valve state from {user} for valve {valve_id}: {state_str}")
                            error_msg = f"Invalid valve state: {state_str}"
                            failed_valves[valve_id_str] = error_msg
                            self._website_logger.log_data([user, "error", error_msg])
                            continue

                        self._controller.set_valve(id=valve_id, state=state_enum)
                        if settings.PRINT_WEBSITE_STATUS:
                            print(f"WEBSITE STATUS: User {user} set valve {valve_id} to {state_str}")
                        self._website_logger.log_data([user, "action", f"Set valve {valve_id} to {state_str}"])
                            
                    except ValueError as e:
                        if settings.PRINT_WEBSITE_ERRORS:
                            print(f"WEBSITE ERROR: Failed to set valve state for {user}: {e}")
                        error_msg = f"WEBSITE ERROR: Failed to set valve state: {e}"
                        failed_valves[valve_id_str] = error_msg
                        self._website_logger.log_data([user, "error", error_msg])
                        
                    except Exception as e:
                        if settings.PRINT_WEBSITE_ERRORS:
                            print(f"WEBSITE ERROR: Failed to set valve {valve_id_str} state for {user}: {e}")
                        error_msg = f"WEBSITE ERROR: Failed to set valve {valve_id_str} state: {e}"
                        failed_valves[valve_id_str] = error_msg
                        self._website_logger.log_data([user, "error", error_msg])
                
                if len(failed_valves) == 0:
                    return jsonify({"status": "success"})
                else:
                    return jsonify({
                        "status": "error",
                        "failed_valves": failed_valves
                    }), 400

        @self._app.post("/api/pulse_valves")
        def pulse_valves():
            """
            Pulses multiple valves based on provided dict (valve_id: duration)
            """
            user = request.remote_addr
            with self._thread_lock:
                if self._shutdown_flag:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: User attempted to pulse valves while website shut down.")
                    self._website_logger.log_data([user, "error", "Attempted to pulse valves while website shut down."])
                    return jsonify({"status": "error", "message": "Website has been shut down"}), 503
                
                # Block valve operations while executing or safing
                if self._currently_executing is not None:
                    exec_user = self._currently_executing["user"]
                    return jsonify({"status": "error", "message": f"Cannot pulse valves while step is executing (by {exec_user})"}), 409
                
                if self._safing_system is not None:
                    safing_user = self._safing_system["user"]
                    return jsonify({"status": "error", "message": f"Cannot pulse valves while system is being safed (by {safing_user})"}), 409
                
                if not request.is_json:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: Pulse valves request from {user} missing JSON body")
                    self._website_logger.log_data([user, "error", "Pulse valves request missing JSON body"])
                    return jsonify({"status": "error", "message": "Pulse valves request missing JSON body"}), 400

                data = request.get_json()
                if not isinstance(data, dict):
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: Pulse valves request from {user} body must be a dict")
                    self._website_logger.log_data([user, "error", "Pulse valves request body must be a dict"])
                    return jsonify({"status": "error", "message": "Request body must be a dict"}), 400
            
                if len(data) == 0:
                    return jsonify({"status": "success"})

                failed_valves: Dict[str, str] = {}
                for valve_id_str, duration in data.items():
                    try:
                        try:
                            valve_id = int(valve_id_str)
                        except (ValueError, TypeError):
                            if settings.PRINT_WEBSITE_ERRORS:
                                print(f"WEBSITE ERROR: Invalid valve ID from {user}: {valve_id_str}")
                            error_msg = f"Invalid valve ID: {valve_id_str}"
                            failed_valves[valve_id_str] = error_msg
                            self._website_logger.log_data([user, "error", error_msg])
                            continue
                        
                        try:
                            duration = float(duration)
                        except (ValueError, TypeError):
                            if settings.PRINT_WEBSITE_ERRORS:
                                print(f"WEBSITE ERROR: Invalid duration for valve {valve_id} from {user}: {duration}")
                            error_msg = f"Duration for valve {valve_id} must be a number"
                            failed_valves[valve_id_str] = error_msg
                            self._website_logger.log_data([user, "error", error_msg])
                            continue

                        self._controller.pulse_valve(id=valve_id, duration=duration)
                        if settings.PRINT_WEBSITE_STATUS:
                            print(f"WEBSITE STATUS: User {user} pulsed valve {valve_id} for {duration}s")
                        self._website_logger.log_data([user, "action", f"Pulsed valve {valve_id} for {duration}s"])
                            
                    except (ValueError, RuntimeError) as e:
                        if settings.PRINT_WEBSITE_ERRORS:
                            print(f"WEBSITE ERROR: Failed to pulse valve {valve_id_str} for {user}: {e}")
                        error_msg = str(e)
                        failed_valves[valve_id_str] = error_msg
                        self._website_logger.log_data([user, "error", f"Failed to pulse valve {valve_id_str}: {e}"])
                        
                    except Exception as e:
                        if settings.PRINT_WEBSITE_ERRORS:
                            print(f"WEBSITE ERROR: Failed to pulse valve {valve_id_str} for {user}: {e}")
                        error_msg = f"Internal error pulsing valve {valve_id_str}"
                        failed_valves[valve_id_str] = error_msg
                        self._website_logger.log_data([user, "error", error_msg])
                
                if len(failed_valves) == 0:
                    return jsonify({"status": "success"})
                else:
                    return jsonify({
                        "status": "error",
                        "failed_valves": failed_valves
                    }), 400

        @self._app.get("/api/get_procedures")
        def get_procedures():
            """
            Gets the list of procedures.
            """
            user = request.remote_addr
            with self._thread_lock:
                if self._shutdown_flag:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: User attempted to get procedures while website shut down.")
                    self._website_logger.log_data([user, "error", "Attempted to get procedures while website shut down."])
                    return jsonify({"status": "error", "message": "Website has been shut down"}), 503
                try:
                    return jsonify(self._procedures)
                except Exception as e:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: Failed to get procedures from {user}: {e}")
                    self._website_logger.log_data([user, "error", f"Failed to get procedures: {e}"])
                    return jsonify({"status": "error", "message": "Failed to get procedures"}), 500

        @self._app.get("/api/get_invalid_valve_states")
        def get_invalid_valve_states():
            """
            Gets the list of invalid valve states.
            """
            user = request.remote_addr
            with self._thread_lock:
                if self._shutdown_flag:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: User attempted to get invalid valve states while website shut down.")
                    self._website_logger.log_data([user, "error", "Attempted to get invalid valve states while website shut down."])
                    return jsonify({"status": "error", "message": "Website has been shut down"}), 503
                try:
                    return jsonify(self._invalid_valve_states)
                except Exception as e:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: Failed to get invalid valve states from {user}: {e}")
                    self._website_logger.log_data([user, "error", f"Failed to get invalid valve states: {e}"])
                    return jsonify({"status": "error", "message": "Failed to get invalid valve states"}), 500

        @self._app.get("/api/get_website_title")
        def get_website_title():
            """
            Gets the website title.
            """
            user = request.remote_addr
            with self._thread_lock:
                if self._shutdown_flag:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: User attempted to get website title while website shut down.")
                    self._website_logger.log_data([user, "error", "Attempted to get website title while website shut down."])
                    return jsonify({"status": "error", "message": "Website has been shut down"}), 503
                try:
                    return jsonify({"title": self._website_title})
                except Exception as e:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: Failed to get website title from {user}: {e}")
                    self._website_logger.log_data([user, "error", f"Failed to get website title: {e}"])
                    return jsonify({"status": "error", "message": "Failed to get website title"}), 500

        @self._app.get("/api/get_safe_mode")
        def get_safe_mode():
            """
            Gets the "safe mode" status for the user.
            """
            user = request.remote_addr
            with self._thread_lock:
                if self._shutdown_flag:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: User attempted to get safe mode while website shut down.")
                    self._website_logger.log_data([user, "error", "Attempted to get safe mode while website shut down."])
                    return jsonify({"status": "error", "message": "Website has been shut down"}), 503
                else:
                    return jsonify({"safe_mode": self._safe_mode})
                
        @self._app.post("/api/set_safe_mode")
        def set_safe_mode():
            """
            Sets the "safe mode" status for the user.
            """
            user = request.remote_addr
            with self._thread_lock:
                if self._shutdown_flag:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: User attempted to set safe mode while website shut down.")
                    self._website_logger.log_data([user, "error", "Attempted to set safe mode while website shut down."])
                    return jsonify({"status": "error", "message": "Website has been shut down"}), 503
                
                if not request.is_json:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: Set safe mode request from {user} missing JSON body")
                    self._website_logger.log_data([user, "error", "Set safe mode request missing JSON body"])
                    return jsonify({"status": "error", "message": "Set safe mode request missing JSON body"}), 400

                data = request.get_json()
                safe_mode = data.get("safe_mode")
                if safe_mode is None:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: Set safe mode request from {user} missing 'safe_mode' field")
                    self._website_logger.log_data([user, "error", "Set safe mode request missing 'safe_mode' field"])
                    return jsonify({"status": "error", "message": "Missing 'safe_mode' field"}), 400
                
                if not isinstance(safe_mode, bool):
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: 'safe_mode' field from {user} must be a boolean")
                    self._website_logger.log_data([user, "error", "'safe_mode' field must be a boolean"])
                    return jsonify({"status": "error", "message": "'safe_mode' field must be a boolean"}), 400
                
                self._safe_mode = safe_mode
                if safe_mode:
                    self._last_user_heartbeat = time.time()
                return jsonify({"status": "success"})

        @self._app.post("/api/safe_system")
        def safe_system():
            """
            Triggers a manual safe system operation. Finds the first safe state with 
            requirements met and executes its actions. Blocks other operations while running.
            """
            user = request.remote_addr
            with self._thread_lock:
                if self._shutdown_flag:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: User attempted to safe system while website shut down.")
                    self._website_logger.log_data([user, "error", "Attempted to safe system while website shut down."])
                    return jsonify({"status": "error", "message": "Website has been shut down"}), 503
                
                # Check if system is already being safed
                if self._safing_system is not None:
                    safing_user = self._safing_system["user"]
                    return jsonify({
                        "status": "error", 
                        "message": f"System is already being safed by {safing_user}",
                        "safing": {"user": safing_user}
                    }), 409
                
                # Check if a step is executing
                if self._currently_executing is not None:
                    exec_user = self._currently_executing["user"]
                    exec_step = self._currently_executing["step_index"]
                    exec_proc = self._currently_executing["procedure_index"]
                    return jsonify({
                        "status": "error",
                        "message": f"Cannot safe system while step is executing (by {exec_user})",
                        "executing": {
                            "procedure_index": exec_proc,
                            "step_index": exec_step,
                            "user": exec_user
                        }
                    }), 409
                
                # Mark system as being safed
                self._safing_system = {
                    "user": user,
                    "start_time": time.time()
                }
                
                if settings.PRINT_WEBSITE_STATUS:
                    print(f"WEBSITE STATUS: User {user} initiated safe system")
                self._website_logger.log_data([user, "action", "Initiated safe system"])
                
                # Inner function to execute safe system in background thread
                def safe_system_thread() -> None:
                    # Find the first safe state whose requirements are met
                    safe_state_executed = False
                    safe_state_name = None
                    
                    for safe_state in self._system_safe_states:
                        state_name = safe_state.get("name", "Unnamed")
                        requirements = safe_state.get("requirements", [])
                        
                        # Check if all requirements are met
                        requirements_met = all(self._check_safe_state_requirement(req) for req in requirements) if requirements else True
                        
                        if requirements_met:
                            safe_state_name = state_name
                            if settings.PRINT_WEBSITE_STATUS:
                                print(f"WEBSITE STATUS: Executing safe state '{state_name}'")
                            self._website_logger.log_data([user, "action", f"Executing safe state '{state_name}'"])
                            
                            actions = safe_state.get("actions", [])
                            success = self._execute_actions(actions, user=user)
                            
                            with self._thread_lock:
                                self._safing_system = None
                                
                            if success:
                                if settings.PRINT_WEBSITE_STATUS:
                                    print(f"WEBSITE STATUS: Safe state '{state_name}' completed successfully")
                                self._website_logger.log_data([user, "action", f"Safe state '{state_name}' completed"])
                            else:
                                if settings.PRINT_WEBSITE_ERRORS:
                                    print(f"WEBSITE ERROR: Safe state '{state_name}' execution failed")
                                self._website_logger.log_data([user, "error", f"Safe state '{state_name}' execution failed"])
                            
                            safe_state_executed = True
                            break
                    
                    if not safe_state_executed:
                        with self._thread_lock:
                            self._safing_system = None
                        if settings.PRINT_WEBSITE_STATUS:
                            print(f"WEBSITE STATUS: No safe state requirements met, no action taken")
                        self._website_logger.log_data([user, "status", "No safe state requirements met"])
                
                # Start safe system execution in background thread
                thread = threading.Thread(target=safe_system_thread, daemon=True)
                thread.start()
                
                return jsonify({"status": "success", "message": "Safe system initiated"})

        @self._app.get("/api/get_procedure_status")
        def get_procedure_status():
            """
            Gets the completion status of all steps in all procedures and current execution state.
            Returns: {
                "completion": {procedure_index: [completed_step_indices]},
                "executing": {"procedure_index": int, "step_index": int, "user": str} or null
            }
            """
            user = request.remote_addr
            with self._thread_lock:
                if self._shutdown_flag:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: User attempted to get procedure status while website shut down.")
                    self._website_logger.log_data([user, "error", "Attempted to get procedure status while website shut down."])
                    return jsonify({"status": "error", "message": "Website has been shut down"}), 503
                try:
                    completion = {str(k): list(v) for k, v in self._procedure_step_completion.items()}
                    executing = None
                    if self._currently_executing:
                        executing = {
                            "procedure_index": self._currently_executing["procedure_index"],
                            "step_index": self._currently_executing["step_index"],
                            "user": self._currently_executing["user"]
                        }
                    return jsonify({
                        "completion": completion,
                        "executing": executing
                    })
                except Exception as e:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: Failed to get procedure status from {user}: {e}")
                    self._website_logger.log_data([user, "error", f"Failed to get procedure status: {e}"])
                    return jsonify({"status": "error", "message": "Failed to get procedure status"}), 500

        @self._app.get("/api/is_safing")
        def is_safing():
            """
            Gets whether the system is currently being safed.
            Returns: {"safing": bool, "user": str or null}
            """
            user = request.remote_addr
            with self._thread_lock:
                if self._shutdown_flag:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: User attempted to get safing status while website shut down.")
                    self._website_logger.log_data([user, "error", "Attempted to get safing status while website shut down."])
                    return jsonify({"status": "error", "message": "Website has been shut down"}), 503
                try:
                    if self._safing_system:
                        return jsonify({
                            "safing": True,
                            "user": self._safing_system["user"]
                        })
                    else:
                        return jsonify({
                            "safing": False,
                            "user": None
                        })
                except Exception as e:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: Failed to get safing status from {user}: {e}")
                    self._website_logger.log_data([user, "error", f"Failed to get safing status: {e}"])
                    return jsonify({"status": "error", "message": "Failed to get safing status"}), 500

        @self._app.post("/api/start_step_execution")
        def start_step_execution():
            """
            Starts executing a step. The server executes all step actions in a background thread.
            Only one step can execute at a time across all users.
            Request body: {"procedure_index": int, "step_index": int}
            """
            user = request.remote_addr
            with self._thread_lock:
                if self._shutdown_flag:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: User attempted to start step execution while website shut down.")
                    self._website_logger.log_data([user, "error", "Attempted to start step execution while website shut down."])
                    return jsonify({"status": "error", "message": "Website has been shut down"}), 503
                
                if not request.is_json:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: Start step execution request from {user} missing JSON body")
                    self._website_logger.log_data([user, "error", "Start step execution request missing JSON body"])
                    return jsonify({"status": "error", "message": "Request missing JSON body"}), 400

                data = request.get_json()
                
                procedure_index = data.get("procedure_index")
                if procedure_index is None:
                    return jsonify({"status": "error", "message": "Missing 'procedure_index' field"}), 400
                try:
                    procedure_index = int(procedure_index)
                except (ValueError, TypeError):
                    return jsonify({"status": "error", "message": "'procedure_index' must be an integer"}), 400
                
                step_index = data.get("step_index")
                if step_index is None:
                    return jsonify({"status": "error", "message": "Missing 'step_index' field"}), 400
                try:
                    step_index = int(step_index)
                except (ValueError, TypeError):
                    return jsonify({"status": "error", "message": "'step_index' must be an integer"}), 400
                
                # Validate indices
                if procedure_index < 0 or procedure_index >= len(self._procedures):
                    return jsonify({"status": "error", "message": f"Invalid procedure index: {procedure_index}"}), 400
                
                procedure = self._procedures[procedure_index]
                if step_index < 0 or step_index >= len(procedure["steps"]):
                    return jsonify({"status": "error", "message": f"Invalid step index: {step_index}"}), 400
                
                # Check if system is being safed
                if self._safing_system is not None:
                    safing_user = self._safing_system["user"]
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: User {user} attempted to start step execution while system is being safed by {safing_user}")
                    self._website_logger.log_data([user, "error", f"Cannot start step: system being safed by {safing_user}"])
                    return jsonify({
                        "status": "error",
                        "message": f"Cannot execute step while system is being safed (by {safing_user})",
                        "safing": {"user": safing_user}
                    }), 409
                
                # Check if another step is already executing
                if self._currently_executing is not None:
                    exec_proc = self._currently_executing["procedure_index"]
                    exec_step = self._currently_executing["step_index"]
                    exec_user = self._currently_executing["user"]
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: User {user} attempted to start step execution while step {exec_step} in procedure {exec_proc} is already executing by {exec_user}")
                    self._website_logger.log_data([user, "error", f"Step already executing: procedure {exec_proc}, step {exec_step} by {exec_user}"])
                    return jsonify({
                        "status": "error",
                        "message": "Another step is already being executed",
                        "executing": {
                            "procedure_index": exec_proc,
                            "step_index": exec_step,
                            "user": exec_user
                        }
                    }), 409
                
                # Mark step as executing
                self._currently_executing = {
                    "procedure_index": procedure_index,
                    "step_index": step_index,
                    "user": user,
                    "start_time": time.time()
                }
                
                step = procedure["steps"][step_index]
                step_name = step["name"]
                if settings.PRINT_WEBSITE_STATUS:
                    print(f"WEBSITE STATUS: User {user} started executing step '{step_name}' (procedure {procedure_index}, step {step_index})")
                self._website_logger.log_data([user, "action", f"Started executing step '{step_name}' (procedure {procedure_index}, step {step_index})"])
                
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
                            self._website_logger.log_data([user, "action", f"Step '{step_name}' completed (procedure {procedure_index}, step {step_index})"])
                        else:
                            if settings.PRINT_WEBSITE_STATUS:
                                print(f"WEBSITE STATUS: Step '{step_name}' execution ended without completion (procedure {procedure_index}, step {step_index})")
                            self._website_logger.log_data([user, "action", f"Step '{step_name}' ended without completion (procedure {procedure_index}, step {step_index})"])

                # Start execution in background thread
                exec_thread = threading.Thread(
                    target=execute_step_thread,
                    daemon=True
                )
                exec_thread.start()
                
                return jsonify({"status": "success"})

        @self._app.post("/api/set_step_completion")
        def set_step_completion():
            """
            Manually sets a step's completion status without executing it.
            Request body: {"procedure_index": int, "step_index": int, "completed": bool}
            """
            user = request.remote_addr
            with self._thread_lock:
                if self._shutdown_flag:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: User attempted to set step completion while website shut down.")
                    self._website_logger.log_data([user, "error", "Attempted to set step completion while website shut down."])
                    return jsonify({"status": "error", "message": "Website has been shut down"}), 503
                
                if not request.is_json:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: Set step completion request from {user} missing JSON body")
                    self._website_logger.log_data([user, "error", "Set step completion request missing JSON body"])
                    return jsonify({"status": "error", "message": "Request missing JSON body"}), 400

                data = request.get_json()
                
                procedure_index = data.get("procedure_index")
                if procedure_index is None:
                    return jsonify({"status": "error", "message": "Missing 'procedure_index' field"}), 400
                try:
                    procedure_index = int(procedure_index)
                except (ValueError, TypeError):
                    return jsonify({"status": "error", "message": "'procedure_index' must be an integer"}), 400
                
                step_index = data.get("step_index")
                if step_index is None:
                    return jsonify({"status": "error", "message": "Missing 'step_index' field"}), 400
                try:
                    step_index = int(step_index)
                except (ValueError, TypeError):
                    return jsonify({"status": "error", "message": "'step_index' must be an integer"}), 400
                
                completed = data.get("completed")
                if completed is None:
                    return jsonify({"status": "error", "message": "Missing 'completed' field"}), 400
                if not isinstance(completed, bool):
                    return jsonify({"status": "error", "message": "'completed' must be a boolean"}), 400
                
                # Validate indices
                if procedure_index < 0 or procedure_index >= len(self._procedures):
                    return jsonify({"status": "error", "message": f"Invalid procedure index: {procedure_index}"}), 400
                
                procedure = self._procedures[procedure_index]
                if step_index < 0 or step_index >= len(procedure["steps"]):
                    return jsonify({"status": "error", "message": f"Invalid step index: {step_index}"}), 400
                
                # Update completion status
                if procedure_index not in self._procedure_step_completion:
                    self._procedure_step_completion[procedure_index] = set()
                
                if completed:
                    self._procedure_step_completion[procedure_index].add(step_index)
                else:
                    self._procedure_step_completion[procedure_index].discard(step_index)
                
                step_name = procedure["steps"][step_index]["name"]
                if settings.PRINT_WEBSITE_STATUS:
                    status_msg = "completed" if completed else "incomplete"
                    print(f"WEBSITE STATUS: User {user} marked step '{step_name}' as {status_msg} (procedure {procedure_index}, step {step_index})")
                self._website_logger.log_data([user, "action", f"Marked step '{step_name}' as {'completed' if completed else 'incomplete'} (procedure {procedure_index}, step {step_index})"])
                
                return jsonify({"status": "success"})

        @self._app.post("/api/reset_procedure")
        def reset_procedure():
            """
            Resets all step completion statuses for a procedure.
            Request body: {"procedure_index": int}
            """
            user = request.remote_addr
            with self._thread_lock:
                if self._shutdown_flag:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: User attempted to reset procedure while website shut down.")
                    self._website_logger.log_data([user, "error", "Attempted to reset procedure while website shut down."])
                    return jsonify({"status": "error", "message": "Website has been shut down"}), 503
                
                if not request.is_json:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: Reset procedure request from {user} missing JSON body")
                    self._website_logger.log_data([user, "error", "Reset procedure request missing JSON body"])
                    return jsonify({"status": "error", "message": "Request missing JSON body"}), 400

                data = request.get_json()
                
                procedure_index = data.get("procedure_index")
                if procedure_index is None:
                    return jsonify({"status": "error", "message": "Missing 'procedure_index' field"}), 400
                try:
                    procedure_index = int(procedure_index)
                except (ValueError, TypeError):
                    return jsonify({"status": "error", "message": "'procedure_index' must be an integer"}), 400
                
                # Validate index
                if procedure_index < 0 or procedure_index >= len(self._procedures):
                    return jsonify({"status": "error", "message": f"Invalid procedure index: {procedure_index}"}), 400
                
                # Check if any step in this procedure is currently executing
                if self._currently_executing is not None and self._currently_executing["procedure_index"] == procedure_index:
                    return jsonify({
                        "status": "error",
                        "message": "Cannot reset procedure while a step is executing"
                    }), 409
                
                # Clear completion status for this procedure
                if procedure_index in self._procedure_step_completion:
                    del self._procedure_step_completion[procedure_index]
                
                procedure_name = self._procedures[procedure_index]["name"]
                if settings.PRINT_WEBSITE_STATUS:
                    print(f"WEBSITE STATUS: User {user} reset procedure '{procedure_name}' (index {procedure_index})")
                self._website_logger.log_data([user, "action", f"Reset procedure '{procedure_name}' (index {procedure_index})"])
                
                return jsonify({"status": "success"})

        @self._app.get("/")
        def index():
            """
            Serves the main HTML page
            """
            return render_template('index.html')

        if settings.PRINT_WEBSITE_STATUS:
            print(f"WEBSITE STATUS: Website running...")
            print(f"WEBSITE INFO: Website id: {id(self)}")
            print(f"WEBSITE INFO: Controller id: {id(self._controller)}")
            print(f"WEBSITE INFO: Website title: {self._website_title}")
            print(f"WEBSITE INFO: Website port: {self._port}")
            print(f"WEBSITE INFO: Polling rate: {self._polling_rate}Hz")
            print(f"WEBSITE INFO: Heartbeat timeout: {self._heartbeat_timeout}s")
            print(f"WEBSITE INFO: Safe state timeout: {self._safe_state_timeout}s")
            print(f"WEBSITE INFO: Website logger: {str(self._website_logger)}")
            print(f"WEBSITE INFO: System safe states: {self._system_safe_states}")
            print(f"WEBSITE INFO: Invalid valve states: {self._invalid_valve_states}")
            
        self._website_logger.log_data(["system", "status", "Server started"])
        self._website_logger.log_data(["system", "info", f"Website id: {id(self)}"])
        self._website_logger.log_data(["system", "info", f"Controller id: {id(self._controller)}"])
        self._website_logger.log_data(["system", "info", f"Website title: {self._website_title}"])
        self._website_logger.log_data(["system", "info", f"Website port: {self._port}"])
        self._website_logger.log_data(["system", "info", f"Polling rate: {self._polling_rate}Hz"])
        self._website_logger.log_data(["system", "info", f"Heartbeat timeout: {self._heartbeat_timeout}s"])
        self._website_logger.log_data(["system", "info", f"Safe state timeout: {self._safe_state_timeout}s"])
        self._website_logger.log_data(["system", "info", f"Website logger: {str(self._website_logger)}"])
        self._website_logger.log_data(["system", "info", f"System safe states: {self._system_safe_states}"])
        self._website_logger.log_data(["system", "info", f"Invalid valve states: {self._invalid_valve_states}"])

        # Start background thread to update website data
        update_website_thread = threading.Thread(target = self._update_website, daemon = True)
        update_website_thread.start()

        # Start flask application (website) in separate thread
        if not settings.PRINT_FLASK_REQUESTS:
            log = logging.getLogger('werkzeug')
            log.disabled = True
        flask_thread = threading.Thread(
            target = lambda: self._app.run(host = '0.0.0.0', port = self._port, threaded = True),
            daemon = True
        )
        flask_thread.start()

    @classmethod
    def from_config(cls, controller: Controller, config: Dict) -> "ControllerWebsite":
        """
        Initializes a ControllerWebsite object from a configuration dictionary.
        
        Args:
            controller: The Controller object to interface with.
            config: The target configuration dict.
        """
        if 'general_config' not in config:
            raise KeyError(f"Website config missing key: 'general_config'")
        if 'invalid_valve_states' not in config:
            raise KeyError(f"Website config missing key: 'invalid_valve_states'")
        if 'procedures' not in config:
            raise KeyError(f"Website config missing key: 'procedures'")
        
        if 'port' not in config['general_config']:
            raise KeyError(f"Website config missing key: 'general_config.port'")
        if 'polling_rate' not in config['general_config']:
            raise KeyError(f"Website config missing key: 'general_config.polling_rate'")
        if 'heartbeat_timeout' not in config['general_config']:
            raise KeyError(f"Website config missing key: 'general_config.heartbeat_timeout'")
        if 'website_log_path' not in config['general_config']:
            raise KeyError(f"Website config missing key: 'general_config.website_log_path'")
        if 'safe_state_timeout' not in config['general_config']:
            raise KeyError(f"Website config missing key: 'general_config.safe_state_timeout'")
        if 'website_title' not in config['general_config']:
            raise KeyError(f"Website config missing key: 'general_config.website_title'")
        if 'system_safe_states' not in config:
            raise KeyError(f"Website config missing key: 'system_safe_states'")
        
        try:
            port = int(config['general_config']['port'])
        except (ValueError, TypeError):
            raise ValueError(f"Website config 'general_config.port' must be an integer, got: {type(config['general_config']['port']).__name__}")
        
        try:
            polling_rate = float(config['general_config']['polling_rate'])
        except (ValueError, TypeError):
            raise ValueError(f"Website config 'general_config.polling_rate' must be a number, got: {type(config['general_config']['polling_rate']).__name__}")
        
        try:
            heartbeat_timeout = float(config['general_config']['heartbeat_timeout'])
        except (ValueError, TypeError):
            raise ValueError(f"Website config 'general_config.heartbeat_timeout' must be a number, got: {type(config['general_config']['heartbeat_timeout']).__name__}")
        
        website_log_path = config['general_config']['website_log_path']
        if not isinstance(website_log_path, str):
            raise ValueError(f"Website config 'general_config.website_log_path' must be a string, got: {type(website_log_path).__name__}")
        
        website_title = config['general_config']['website_title']
        if not isinstance(website_title, str):
            raise ValueError(f"Website config 'general_config.website_title' must be a string, got: {type(website_title).__name__}")
        
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
            port = port,
            polling_rate = polling_rate,
            heartbeat_timeout = heartbeat_timeout,
            safe_state_timeout = safe_state_timeout,
            website_log_path = website_log_path,
            website_title = website_title,
            system_safe_states = system_safe_states,
            invalid_valve_states = invalid_valve_states,
            procedures = procedures
        )

    def __del__(self) -> None:
        self.shutdown()

    def shutdown(self) -> None:
        """
        Shuts down the website. After this function is called, calls to other methods will raise an exception.
        """
        with self._thread_lock:
            if self._shutdown_flag:
                return
            self._shutdown_flag = True
            if settings.PRINT_WEBSITE_STATUS:
                print(f"WEBSITE STATUS: Website shutting down")
            self._website_logger.log_data(["system", "status", "Server shutting down"])
