from typing import List, Optional
import settings
from valve import Valve, ValveState
from pressure_sensor import PressureSensor
from logger import Logger
import threading
import time

# Maximum sensor data rate in Hz
MAX_SENSOR_DATA_RATE = 1000.0

class Controller:
    """
    Class which represents the controller managing valves and pressure sensors.
    """
    
    def _read_sensors(self) -> None:
        """
        Background thread method to continuously read pressure sensors.
        """
        interval = 1.0 / self._sensor_data_rate
        while not self._shutdown_flag:
            with self._read_sensor_lock:
                for i, sensor in enumerate(self._pressure_sensor_list):
                    try:
                        self._current_pressure_list[i] = sensor.pressure
                    except Exception as e:
                        if settings.PRINT_CONTROLLER_ERRORS:
                            print(f"CONTROLLER ERROR: Failed to read sensor {sensor.id}: {e}")
                        self._controller_logger.log_data(["error", f"Failed to read sensor {sensor.id}: {e}"])
                try:
                    self._sensor_data_logger.log_data([str(pressure) for pressure in self._current_pressure_list])
                except Exception as e:
                    if settings.PRINT_CONTROLLER_ERRORS:
                        print(f"CONTROLLER ERROR: Failed to log sensor data: {e}")
                    self._controller_logger.log_data(["error", f"Failed to log sensor data: {e}"])
            time.sleep(interval)
    
    def __init__(self, valve_list: List[Valve], pressure_sensor_list: List[PressureSensor], sensor_data_rate: float, 
                 sensor_data_log_path: str, valve_data_log_path: str, controller_log_path: str) -> None:
        """
        Initializes a Controller object with the given parameters.
        
        Args:
            valve_list: A list of Valve objects managed by this controller.
            pressure_sensor_list: A list of PressureSensor objects managed by this controller.
            sensor_data_rate: The rate (in Hz) at which pressure sensor data is queried.
            sensor_data_log_path: Path to file to use for logging sensor data.
            valve_data_log_path: Path to file to use for logging valve data.
            controller_log_path: Path to file to use for logging controller status/error data.
        """
        _valve_list = list(valve_list)
        _pressure_sensor_list = list(pressure_sensor_list)
        
        if sensor_data_rate < 0.0:
            raise ValueError(f"Sensor data rate is invalid: {sensor_data_rate} < 0.0")
        if sensor_data_rate > MAX_SENSOR_DATA_RATE:
            raise ValueError(f"Sensor data rate is invalid: {sensor_data_rate} > {MAX_SENSOR_DATA_RATE}")
        
        valve_ids = set()
        for valve in _valve_list:
            if valve.id in valve_ids:
                raise ValueError(f"Duplicate valve ID found in controller config: {valve.id}")
            valve_ids.add(valve.id)
        
        pressure_sensor_ids = set()
        for sensor in _pressure_sensor_list:
            if sensor.id in pressure_sensor_ids:
                raise ValueError(f"Duplicate pressure sensor ID found in controller config: {sensor.id}")
            pressure_sensor_ids.add(sensor.id)

        self._valve_list = _valve_list
        self._pressure_sensor_list = _pressure_sensor_list
        self._sensor_data_rate = sensor_data_rate
        self._current_pressure_list = [0.0 for _ in _pressure_sensor_list]
        self._shutdown_flag = False
        self._read_sensor_lock = threading.Lock()
        
        if len(_pressure_sensor_list) > 0:
            self._sensor_data_logger = Logger(
                path = sensor_data_log_path,
                col = [f"{sensor.id}: {sensor.name}" for sensor in _pressure_sensor_list]
            )
        else:
            self._sensor_data_logger = None
            
        if len(_valve_list) > 0:
            self._valve_data_logger = Logger(
                path = valve_data_log_path,
                col = [f"{valve.id}: {valve.name}" for valve in _valve_list]
            )
        else:
            self._valve_data_logger = None

        self._controller_logger = Logger(
            path = controller_log_path,
            col = ["type", "message"]
        )
        
        if len(_pressure_sensor_list) > 0:
            self._read_sensors_thread = threading.Thread(target = self._read_sensors)
            self._read_sensors_thread.start()
        else:
            self._read_sensors_thread = None
            
        if settings.PRINT_CONTROLLER_STATUS:
            print("CONTROLLER STATUS: Controller started")
            print(f"CONTROLLER INFO: Controller id: {id(self)}")
            print(f"CONTROLLER INFO: Valves: {[str(valve) for valve in self._valve_list]}")
            print(f"CONTROLLER INFO: Pressure Sensors: {[str(sensor) for sensor in self._pressure_sensor_list]}")
            print(f"CONTROLLER INFO: Sensor Data Rate: {self._sensor_data_rate} Hz")
            print(f"CONTROLLER INFO: Sensor data logger: {str(self._sensor_data_logger)}")
            print(f"CONTROLLER INFO: Valve data logger: {str(self._valve_data_logger)}")
            print(f"CONTROLLER INFO: Controller logger: {str(self._controller_logger)}")
            
        self._controller_logger.log_data(["status", "Controller started"])
        self._controller_logger.log_data(["info", f"Controller id: {id(self)}"])
        self._controller_logger.log_data(["info", f"Valves: {[str(valve) for valve in self._valve_list]}"])
        self._controller_logger.log_data(["info", f"Pressure Sensors: {[str(sensor) for sensor in self._pressure_sensor_list]}"])
        self._controller_logger.log_data(["info", f"Sensor Data Rate: {self._sensor_data_rate} Hz"])
        self._controller_logger.log_data(["info", f"Sensor data logger: {str(self._sensor_data_logger)}"])
        self._controller_logger.log_data(["info", f"Valve data logger: {str(self._valve_data_logger)}"])
        self._controller_logger.log_data(["info", f"Controller logger: {str(self._controller_logger)}"])
        
    @classmethod
    def from_config(cls, config: dict) -> "Controller":
        """
        Initializes a Controller object from a configuration dictionary.
        
        Args:
            config: The target configuration dict.
        """
        if 'valve_config' not in config:
            raise KeyError(f"Controller config missing key: 'valve_config'")
        if 'pressure_sensor_config' not in config:
            raise KeyError(f"Controller config missing key: 'pressure_sensor_config'")
        if 'system_config' not in config:
            raise KeyError(f"Controller config missing key: 'system_config'")
        
        if 'pressure_sensor_data_rate' not in config['system_config']:
            raise KeyError(f"Controller config missing key: 'system_config.pressure_sensor_data_rate'")
        if 'pressure_sensor_data_log_path' not in config['system_config']:
            raise KeyError(f"Controller config missing key: 'system_config.pressure_sensor_data_log_path'")
        if 'valve_data_log_path' not in config['system_config']:
            raise KeyError(f"Controller config missing key: 'system_config.valve_data_log_path'")
        if 'controller_log_path' not in config['system_config']:
            raise KeyError(f"Controller config missing key: 'system_config.controller_log_path'")
        
        if not isinstance(config['valve_config'], list):
            raise ValueError(f"Controller config 'valve_config' must be a list, got: {type(config['valve_config']).__name__}")
        if not isinstance(config['pressure_sensor_config'], list):
            raise ValueError(f"Controller config 'pressure_sensor_config' must be a list, got: {type(config['pressure_sensor_config']).__name__}")
        
        valve_list = [Valve.from_config(v_config) for v_config in config['valve_config']]
        pressure_sensor_list = [PressureSensor.from_config(ps_config) for ps_config in config['pressure_sensor_config']]
        
        try:
            sensor_data_rate = float(config['system_config']['pressure_sensor_data_rate'])
        except (ValueError, TypeError):
            raise ValueError(f"Controller config 'system_config.pressure_sensor_data_rate' must be a number, got: {type(config['system_config']['pressure_sensor_data_rate']).__name__}")
        
        sensor_data_log_path = config['system_config']['pressure_sensor_data_log_path']
        if not isinstance(sensor_data_log_path, str):
            raise ValueError(f"Controller config 'system_config.pressure_sensor_data_log_path' must be a string, got: {type(sensor_data_log_path).__name__}")
        
        valve_data_log_path = config['system_config']['valve_data_log_path']
        if not isinstance(valve_data_log_path, str):
            raise ValueError(f"Controller config 'system_config.valve_data_log_path' must be a string, got: {type(valve_data_log_path).__name__}")
        
        controller_log_path = config['system_config']['controller_log_path']
        if not isinstance(controller_log_path, str):
            raise ValueError(f"Controller config 'system_config.controller_log_path' must be a string, got: {type(controller_log_path).__name__}")
   
        return cls(
            valve_list = valve_list,
            pressure_sensor_list = pressure_sensor_list,
            sensor_data_rate = sensor_data_rate,
            sensor_data_log_path = sensor_data_log_path,
            valve_data_log_path = valve_data_log_path,
            controller_log_path = controller_log_path
        )
        
    def __del__(self) -> None:
        self.shutdown()

    @property
    def valve_info(self) -> List[dict]:
        """
        List of ValveInfo objects representing current valve states.
        """
        if self._shutdown_flag:
            raise RuntimeError("Controller has been shut down")
        with self._read_sensor_lock:
            return [{"id": valve.id, "name": valve.name, "default_state": valve.default_state.value, "current_state": valve.state.value} for valve in self._valve_list]

    @property
    def pressure_sensor_info(self) -> List[dict]:
        """
        List of PressureSensorInfo objects representing current pressure sensor states.
        """
        if self._shutdown_flag:
            raise RuntimeError("Controller has been shut down")
        with self._read_sensor_lock:
            return [{"id": sensor.id, "name": sensor.name, "current_pressure": self._current_pressure_list[i]} for i, sensor in enumerate(self._pressure_sensor_list)]
    
    def set_valve(self, id: int, state: ValveState) -> None:
        """
        Sets the state of the valve with the given ID.
        
        Args:
            id: The unique ID of the valve to be set.
            state: The target state for the valve.
        """
        if self._shutdown_flag:
            raise RuntimeError("Controller has been shut down")
        with self._read_sensor_lock:
            for i, valve in enumerate(self._valve_list):
                if valve.id == id:
                    valve.state = state
                    self._valve_data_logger.log_data([str(valve.state.name) for valve in self._valve_list])
                    return
        raise ValueError(f"Controller has no valve with ID: {id}")
        
    def shutdown(self) -> None:
        """
        Shuts down controller. After this function is called, calls to other methods will raise an exception.
        """
        with self._read_sensor_lock:
            if self._shutdown_flag:
                return
            self._shutdown_flag = True
        if self._read_sensors_thread and self._read_sensors_thread.is_alive():
            self._read_sensors_thread.join(timeout = settings.THREAD_JOIN_TIMEOUT)
        if settings.PRINT_CONTROLLER_STATUS:
            print("CONTROLLER STATUS: Controller shutdown")
        self._controller_logger.log_data(["status", "Controller shutdown"])
        

        