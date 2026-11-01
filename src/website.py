import time
import threading
import os
import logging
from typing import Callable, Dict
from flask import Flask, render_template, request, jsonify
from .operations import ControllerOperations, BusyError, ValveChangeError, OperationsShutdownError
from . import settings

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
    Class which represents the web interface for the controller. A thin Flask layer over ControllerOperations:
    each route parses the request, calls the operations object, and turns its exceptions into JSON responses.
    The website itself only owns user heartbeats, the port and the title.
    """

    def _update_website(self) -> None:
        """
        Background thread method to periodically check user heartbeats.
        """
        interval = 1.0 / settings.WEBSITE_THREAD_UPDATE_RATE
        while True:
            with self._thread_lock:
                if self._shutdown_flag:
                    break
                try:
                    current_time = time.time()
                    for user, last_heartbeat in dict(self._user_heartbeats).items():
                        if (current_time - last_heartbeat) > settings.WEBSITE_HEARTBEAT_TIMEOUT:
                            if settings.PRINT_WEBSITE_STATUS:
                                print(f"WEBSITE STATUS: User {user} disconnected.")
                            self._website_logger.log_data([user, "status", "User disconnected"])
                            del self._user_heartbeats[user]
                except Exception as e:
                    if settings.PRINT_WEBSITE_ERRORS:
                        print(f"WEBSITE ERROR: Update website error: {e}")
            time.sleep(interval)

    def _shutdown_response(self, user: str, action: str, status_code: int = 503):
        """
        Logs an attempted request after shutdown and returns the error response.
        """
        if settings.PRINT_WEBSITE_ERRORS:
            print(f"WEBSITE ERROR: User attempted to {action} while website shut down.")
        self._website_logger.log_data([user, "error", f"Attempted to {action} while website shut down."])
        return jsonify({"status": "error", "message": "Website has been shut down"}), status_code

    def _bad_request(self, user: str, message: str, log_message: str = None):
        """
        Logs a malformed request and returns a 400 response.
        """
        log_message = log_message or message
        if settings.PRINT_WEBSITE_ERRORS:
            print(f"WEBSITE ERROR: {log_message} (from {user})")
        self._website_logger.log_data([user, "error", log_message])
        return jsonify({"status": "error", "message": message}), 400

    @staticmethod
    def _error_response(e: Exception):
        """
        Maps an exception raised by ControllerOperations to an HTTP error response.
        """
        if isinstance(e, BusyError):
            return jsonify({"status": "error", "message": e.message, **e.details}), 409
        if isinstance(e, ValveChangeError):
            return jsonify({"status": "error", "failed_valves": e.failed}), 400
        if isinstance(e, OperationsShutdownError):
            return jsonify({"status": "error", "message": str(e)}), 503
        if isinstance(e, ValueError):
            return jsonify({"status": "error", "message": str(e)}), 400
        raise e

    def _run_command(self, command: Callable[[], None], success_body: Dict = None):
        """
        Runs an operations command and maps its exceptions to HTTP responses.
        """
        try:
            command()
        except (BusyError, ValveChangeError, OperationsShutdownError, ValueError) as e:
            return self._error_response(e)
        return jsonify(success_body or {"status": "success"})

    def _run_query(self, user: str, description: str, query: Callable[[], object]):
        """
        Runs an operations query and returns its result as JSON, or a 500 response if it fails.
        """
        try:
            return jsonify(query())
        except OperationsShutdownError as e:
            return jsonify({"status": "error", "message": str(e)}), 503
        except Exception as e:
            if settings.PRINT_WEBSITE_ERRORS:
                print(f"WEBSITE ERROR: Failed to {description} from {user}: {e}")
            self._website_logger.log_data([user, "error", f"Failed to {description}: {e}"])
            return jsonify({"status": "error", "message": f"Failed to {description}"}), 500

    @staticmethod
    def _parse_int_field(data: Dict, field: str):
        """
        Reads an integer field from a request body. Returns (value, error_message).
        """
        value = data.get(field)
        if value is None:
            return None, f"Missing '{field}' field"
        try:
            return int(value), None
        except (ValueError, TypeError):
            return None, f"'{field}' must be an integer"

    def __init__(self, operations: ControllerOperations, port: int, website_title: str) -> None:
        """
        Initializes a ControllerWebsite object and starts the web server.

        Args:
            operations: The ControllerOperations object to interface with.
            port: The port number for the web server.
            website_title: The title to display in the website header.
        """
        if operations is None:
            raise ValueError("Invalid operations object")
        if port < MIN_PORT_VALUE:
            raise ValueError(f"Port number is invalid: {port} < {MIN_PORT_VALUE}")
        if port > MAX_PORT_VALUE:
            raise ValueError(f"Port number is invalid: {port} > {MAX_PORT_VALUE}")

        self._operations = operations
        self._port = port
        self._website_logger = operations.logger
        self._website_title = website_title
        self._shutdown_flag = False
        self._thread_lock = threading.Lock()
        self._user_heartbeats: Dict[str, float] = {}

        self._app = Flask(
            __name__,
            template_folder = WEBSITE_TEMPLATE_FOLDER_PATH,
            static_folder = WEBSITE_STATIC_FOLDER_PATH
        )
        ops = self._operations

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
            if self._shutdown_flag:
                return self._shutdown_response(user, "send heartbeat", status_code = 500)
            with self._thread_lock:
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
            Gets list of info for all valves (id, name, default_state, current_state, is_pulsing, pulse_info).
            """
            user = request.remote_addr
            if self._shutdown_flag:
                return self._shutdown_response(user, "get valve info")
            return self._run_query(user, "get valve info", ops.get_valve_info)

        @self._app.get("/api/get_sensor_info")
        def get_sensor_info():
            """
            Gets list of info for all pressure sensors (id, name, current_pressure)
            """
            user = request.remote_addr
            if self._shutdown_flag:
                return self._shutdown_response(user, "get sensor info")
            return self._run_query(user, "get sensor info", ops.get_sensor_info)

        @self._app.post("/api/set_valve_states")
        def set_valve_states():
            """
            Updates valve states based on provided dict.
            Supports: valve_id: "open", "closed", or "pulse:duration" (e.g., "pulse:1.5")
            """
            user = request.remote_addr
            if self._shutdown_flag:
                return self._shutdown_response(user, "set valve states")

            # Busy check comes before request validation (matches the original endpoint)
            try:
                ops.check_valves_modifiable()
            except (BusyError, OperationsShutdownError) as e:
                return self._error_response(e)

            if not request.is_json:
                return self._bad_request(user, "Set valve states request missing JSON body")
            data = request.get_json()
            if not isinstance(data, dict):
                return self._bad_request(user, "Request body must be a dict", "Set valve states request body must be a dict")

            return self._run_command(lambda: ops.set_valve_states(data, user))

        @self._app.get("/api/get_procedures")
        def get_procedures():
            """
            Gets the list of procedures.
            """
            user = request.remote_addr
            if self._shutdown_flag:
                return self._shutdown_response(user, "get procedures")
            return self._run_query(user, "get procedures", lambda: ops.procedures)

        @self._app.get("/api/get_invalid_valve_states")
        def get_invalid_valve_states():
            """
            Gets the list of invalid valve states.
            """
            user = request.remote_addr
            if self._shutdown_flag:
                return self._shutdown_response(user, "get invalid valve states")
            return self._run_query(user, "get invalid valve states", lambda: ops.invalid_valve_states)

        @self._app.get("/api/get_website_title")
        def get_website_title():
            """
            Gets the website title.
            """
            user = request.remote_addr
            if self._shutdown_flag:
                return self._shutdown_response(user, "get website title")
            return self._run_query(user, "get website title", lambda: {"title": self._website_title})

        @self._app.get("/api/get_safe_mode")
        def get_safe_mode():
            """
            Gets the "safe mode" status.
            """
            user = request.remote_addr
            if self._shutdown_flag:
                return self._shutdown_response(user, "get safe mode")
            return self._run_query(user, "get safe mode", lambda: {"safe_mode": ops.get_safe_mode()})

        @self._app.post("/api/set_safe_mode")
        def set_safe_mode():
            """
            Sets the "safe mode" status.
            """
            user = request.remote_addr
            if self._shutdown_flag:
                return self._shutdown_response(user, "set safe mode")
            if not request.is_json:
                return self._bad_request(user, "Set safe mode request missing JSON body")

            data = request.get_json()
            safe_mode = data.get("safe_mode")
            if safe_mode is None:
                return self._bad_request(user, "Missing 'safe_mode' field", "Set safe mode request missing 'safe_mode' field")
            if not isinstance(safe_mode, bool):
                return self._bad_request(user, "'safe_mode' field must be a boolean")

            return self._run_command(lambda: ops.set_safe_mode(safe_mode, user))

        @self._app.post("/api/safe_system")
        def safe_system():
            """
            Triggers a manual safe system operation. Finds the first safe state with
            requirements met and executes its actions. Blocks other operations while running.
            """
            user = request.remote_addr
            if self._shutdown_flag:
                return self._shutdown_response(user, "safe system")
            return self._run_command(
                lambda: ops.safe_system(user),
                success_body = {"status": "success", "message": "Safe system initiated"}
            )

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
            if self._shutdown_flag:
                return self._shutdown_response(user, "get procedure status")
            return self._run_query(user, "get procedure status", ops.get_procedure_status)

        @self._app.get("/api/is_safing")
        def is_safing():
            """
            Gets whether the system is currently being safed.
            Returns: {"safing": bool, "user": str or null}
            """
            user = request.remote_addr
            if self._shutdown_flag:
                return self._shutdown_response(user, "get safing status")
            return self._run_query(user, "get safing status", ops.get_safing_status)

        @self._app.post("/api/start_step_execution")
        def start_step_execution():
            """
            Starts executing a step. The server executes all step actions in a background thread.
            Only one step can execute at a time across all users.
            Request body: {"procedure_index": int, "step_index": int}
            """
            user = request.remote_addr
            if self._shutdown_flag:
                return self._shutdown_response(user, "start step execution")
            if not request.is_json:
                return self._bad_request(user, "Request missing JSON body", "Start step execution request missing JSON body")

            data = request.get_json()
            procedure_index, error = self._parse_int_field(data, "procedure_index")
            if error:
                return jsonify({"status": "error", "message": error}), 400
            step_index, error = self._parse_int_field(data, "step_index")
            if error:
                return jsonify({"status": "error", "message": error}), 400

            return self._run_command(lambda: ops.start_step(procedure_index, step_index, user))

        @self._app.post("/api/set_step_completion")
        def set_step_completion():
            """
            Manually sets a step's completion status without executing it.
            Request body: {"procedure_index": int, "step_index": int, "completed": bool}
            """
            user = request.remote_addr
            if self._shutdown_flag:
                return self._shutdown_response(user, "set step completion")
            if not request.is_json:
                return self._bad_request(user, "Request missing JSON body", "Set step completion request missing JSON body")

            data = request.get_json()
            procedure_index, error = self._parse_int_field(data, "procedure_index")
            if error:
                return jsonify({"status": "error", "message": error}), 400
            step_index, error = self._parse_int_field(data, "step_index")
            if error:
                return jsonify({"status": "error", "message": error}), 400
            completed = data.get("completed")
            if completed is None:
                return jsonify({"status": "error", "message": "Missing 'completed' field"}), 400
            if not isinstance(completed, bool):
                return jsonify({"status": "error", "message": "'completed' must be a boolean"}), 400

            return self._run_command(lambda: ops.set_step_completion(procedure_index, step_index, completed, user))

        @self._app.post("/api/reset_procedure")
        def reset_procedure():
            """
            Resets all step completion statuses for a procedure.
            Request body: {"procedure_index": int}
            """
            user = request.remote_addr
            if self._shutdown_flag:
                return self._shutdown_response(user, "reset procedure")
            if not request.is_json:
                return self._bad_request(user, "Request missing JSON body", "Reset procedure request missing JSON body")

            data = request.get_json()
            procedure_index, error = self._parse_int_field(data, "procedure_index")
            if error:
                return jsonify({"status": "error", "message": error}), 400

            return self._run_command(lambda: ops.reset_procedure(procedure_index, user))

        @self._app.get("/")
        def index():
            """
            Serves the main HTML page
            """
            return render_template('index.html')

        if settings.PRINT_WEBSITE_STATUS:
            print(f"WEBSITE STATUS: Website running...")
            print(f"WEBSITE INFO: Website id: {id(self)}")
            print(f"WEBSITE INFO: Operations id: {id(self._operations)}")
            print(f"WEBSITE INFO: Website title: {self._website_title}")
            print(f"WEBSITE INFO: Website port: {self._port}")
            print(f"WEBSITE INFO: Polling rate: {settings.WEBSITE_THREAD_UPDATE_RATE}Hz")
            print(f"WEBSITE INFO: Heartbeat timeout: {settings.WEBSITE_HEARTBEAT_TIMEOUT}s")
            print(f"WEBSITE INFO: Safe state timeout: {self._operations.safe_state_timeout}s")
            print(f"WEBSITE INFO: Website logger: {str(self._website_logger)}")
            print(f"WEBSITE INFO: System safe states: {self._operations.system_safe_states}")
            print(f"WEBSITE INFO: Invalid valve states: {self._operations.invalid_valve_states}")

        self._website_logger.log_data(["system", "status", "Server started"])
        self._website_logger.log_data(["system", "info", f"Website id: {id(self)}"])
        self._website_logger.log_data(["system", "info", f"Operations id: {id(self._operations)}"])
        self._website_logger.log_data(["system", "info", f"Website title: {self._website_title}"])
        self._website_logger.log_data(["system", "info", f"Website port: {self._port}"])
        self._website_logger.log_data(["system", "info", f"Polling rate: {settings.WEBSITE_THREAD_UPDATE_RATE}Hz"])
        self._website_logger.log_data(["system", "info", f"Heartbeat timeout: {settings.WEBSITE_HEARTBEAT_TIMEOUT}s"])
        self._website_logger.log_data(["system", "info", f"Website logger: {str(self._website_logger)}"])

        # Start background thread to track user heartbeats
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
    def from_config(cls, operations: ControllerOperations, config: Dict) -> "ControllerWebsite":
        """
        Initializes a ControllerWebsite object from a configuration dictionary.

        Args:
            operations: The ControllerOperations object to interface with.
            config: The target configuration dict.
        """
        if 'general_config' not in config:
            raise KeyError(f"Website config missing key: 'general_config'")
        if 'port' not in config['general_config']:
            raise KeyError(f"Website config missing key: 'general_config.port'")
        if 'website_title' not in config['general_config']:
            raise KeyError(f"Website config missing key: 'general_config.website_title'")

        try:
            port = int(config['general_config']['port'])
        except (ValueError, TypeError):
            raise ValueError(f"Website config 'general_config.port' must be an integer, got: {type(config['general_config']['port']).__name__}")

        website_title = config['general_config']['website_title']
        if not isinstance(website_title, str):
            raise ValueError(f"Website config 'general_config.website_title' must be a string, got: {type(website_title).__name__}")

        return cls(
            operations = operations,
            port = port,
            website_title = website_title
        )

    def __del__(self) -> None:
        self.shutdown()

    def shutdown(self) -> None:
        """
        Shuts down the website. After this function is called, API requests return an error.
        Does not shut down the shared ControllerOperations object.
        """
        with self._thread_lock:
            if self._shutdown_flag:
                return
            self._shutdown_flag = True
            if settings.PRINT_WEBSITE_STATUS:
                print(f"WEBSITE STATUS: Website shutting down")
            self._website_logger.log_data(["system", "status", "Server shutting down"])
