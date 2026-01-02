import time
import threading
import os
import logging
from typing import Dict, List, Optional
from flask import Flask, render_template, request, jsonify
from controller import Controller
from valve import ValveState
from logger import Logger
import settings
from dataclasses import dataclass
 
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
                                print(f"WEBSITE STATUS: Safe mode timeout reached, setting valves to safe states.")
                            self._website_logger.log_data(["system", "status", "Safing system"])
                            for config in self._valve_safe_config:
                                valve_id = int(config["id"])
                                valve_state = ValveState[config["state"].strip().upper()]
                                try:
                                    self._controller.set_valve(id = valve_id, state = valve_state)
                                except Exception as e:
                                    if settings.PRINT_WEBSITE_ERRORS:
                                        print(f"WEBSITE ERROR: Failed to set valve {valve_id} to safe state: {e}")
                                    self._website_logger.log_data(["system", "error", f"Failed to set valve {valve_id} to safe state: {e}"])
                            self._safe_mode = False
                except Exception as e:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: Update website error: {e}")
            time.sleep(interval)

    def __init__(self, controller: Controller, port: int, polling_rate: float, heartbeat_timeout: float, safe_state_timeout: float, website_log_path: str, website_title: str, valve_safe_config: List[dict], invalid_valve_states: dict, procedures: dict) -> None:
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
            valve_safe_config: List of dicts defining safe valve states.
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

        for config in valve_safe_config:
            valve_id_str = config.get("id")
            if valve_id_str is None:
                raise KeyError(f"Valve safe config missing key: \"id\"")
            try:
                valve_id = int(valve_id_str)
            except (ValueError, TypeError):
                raise ValueError(f"Valve safe config has invalid ID (not an integer): {valve_id_str}")
            valve_ids = {int(valve["id"]) for valve in controller.valve_info}
            if valve_id not in valve_ids:
                raise ValueError(f"Valve safe config references unknown valve ID: {valve_id}")
            valve_state_str = config.get("state")
            if valve_state_str is None:
                raise KeyError(f"Valve safe config missing key: \"state\"")
            if not isinstance(valve_state_str, str):
                raise ValueError(f"Valve safe config 'state' must be a string, got: {type(valve_state_str).__name__}")
            try:
                valve_state = ValveState[valve_state_str.strip().upper()]
            except (KeyError, AttributeError):
                raise ValueError(f"Valve safe config has invalid state (not \"open\" or \"closed\"): {valve_state_str}")

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
        self._valve_safe_config = valve_safe_config
        self._invalid_valve_states = invalid_valve_states
        self._procedures = procedures
        self._shutdown_flag = False
        self._safe_mode = False
        self._last_user_heartbeat = 0.0
        self._thread_lock = threading.Lock()
        self._user_heartbeats: Dict[str, float] = {}
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

        @self._app.get("/")
        def index():
            """
            Serves the main HTML page with embedded configuration data
            """
            return render_template(
                'index.html',
                website_title = self._website_title,
                invalid_valve_states = self._invalid_valve_states,
                procedures = self._procedures
            )

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
            print(f"WEBSITE INFO: Valve safe config: {self._valve_safe_config}")
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
        self._website_logger.log_data(["system", "info", f"Valve safe config: {self._valve_safe_config}"])
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
        if 'valve_safe_config' not in config:
            raise KeyError(f"Website config missing key: 'valve_safe_config'")
        
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
        
        valve_safe_config = config['valve_safe_config']
        if not isinstance(valve_safe_config, list):
            raise ValueError(f"Website config 'valve_safe_config' must be a list, got: {type(valve_safe_config).__name__}")
        
        return cls(
            controller = controller,
            port = port,
            polling_rate = polling_rate,
            heartbeat_timeout = heartbeat_timeout,
            safe_state_timeout = safe_state_timeout,
            website_log_path = website_log_path,
            website_title = website_title,
            valve_safe_config = valve_safe_config,
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
