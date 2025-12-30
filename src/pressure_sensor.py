from typing import List, Dict
import board
from busio import I2C
from adafruit_ads1x15.ads1115 import ADS1115
from adafruit_ads1x15.analog_in import AnalogIn

# Number of supported pressure sensors
PS_COUNT = 8

# Minimum possible voltage for pressure sensors
PS_MIN_VOLTAGE = 0.0

# Maximum possible voltage for pressure sensors
PS_MAX_VOLTAGE = 5.0

# Minimum possible pressure for pressure sensors (in PSI)
PS_MIN_PRESSURE = 0.0

# Maximum possible pressure for pressure sensors (in PSI)
PS_MAX_PRESSURE = 10000.0

# Global I2C bus for pressure sensor ADCs
PS_ADC_I2C_BUS = I2C(board.SCL1, board.SDA1)

# List of ADCs used to read pressure sensors
PS_ADC_LIST: List[ADS1115] = [
    ADS1115(i2c = PS_ADC_I2C_BUS, address = 0x48),
    ADS1115(i2c = PS_ADC_I2C_BUS, address = 0x49)
]

# Mapping of pressure sensor IDs to their corresponding ADCs
PS_ADC_MAP: Dict[int, ADS1115] = {
    1: PS_ADC_LIST[0],
    2: PS_ADC_LIST[0],
    3: PS_ADC_LIST[0],
    4: PS_ADC_LIST[0],
    5: PS_ADC_LIST[1],
    6: PS_ADC_LIST[1],
    7: PS_ADC_LIST[1],
    8: PS_ADC_LIST[1]
}

# Mapping of pressure sensor IDs to their corresponding ADC channels
PS_CHANNEL_MAP: Dict[int, int] = {
    1: 0,
    2: 1,
    3: 2,
    4: 3,
    5: 0,
    6: 1,
    7: 2,
    8: 3
}

class PressureSensor:
    """
    Class which represents a pressure sensor connected to the controller.
    """
    
    def __init__(self, id: int, name: str, min_voltage: float, max_voltage: float, min_pressure: float, max_pressure: float) -> None:
        """
        Initializes a PressureSensor object with the given parameters.
        
        Args:
            id: The unique ID of this pressure sensor.
            name: The name of this pressure sensor.
            min_voltage: The minimum voltage output of this pressure sensor.
            max_voltage: The maximum voltage output of this pressure sensor.
            min_pressure: The minimum pressure measurable by this pressure sensor.
            max_pressure: The maximum pressure measurable by this pressure sensor.
        """
        if id > PS_COUNT:
            raise ValueError(f"Pressure sensor has invalid ID: {id} > {PS_COUNT}")
        if id < 1:
            raise ValueError(f"Pressure sensor has invalid ID: {id} < 1")
        if min_voltage < PS_MIN_VOLTAGE:
            raise ValueError(f"Pressure sensor {id} has invalid minimum voltage: {min_voltage} < {PS_MIN_VOLTAGE}")
        if max_voltage > PS_MAX_VOLTAGE:
            raise ValueError(f"Pressure sensor {id} has invalid maximum voltage: {max_voltage} > {PS_MAX_VOLTAGE}")
        if min_voltage >= max_voltage:
            raise ValueError(f"Pressure sensor {id} has invalid voltage range: {min_voltage} >= {max_voltage}")
        if min_pressure < PS_MIN_PRESSURE:
            raise ValueError(f"Pressure sensor {id} has invalid minimum pressure: {min_pressure} < {PS_MIN_PRESSURE}")
        if max_pressure > PS_MAX_PRESSURE:
            raise ValueError(f"Pressure sensor {id} has invalid maximum pressure: {max_pressure} > {PS_MAX_PRESSURE}")
        if min_pressure >= max_pressure:
            raise ValueError(f"Pressure sensor {id} has invalid pressure range: {min_pressure} >= {max_pressure}")
        
        self._id = id
        self.name = name
        self._min_voltage = min_voltage
        self._max_voltage = max_voltage
        self._min_pressure = min_pressure
        self._max_pressure = max_pressure
        self._adc = PS_ADC_MAP[id]
        self._channel = PS_CHANNEL_MAP[id]

    @classmethod
    def from_config(cls, config: Dict) -> "PressureSensor":
        """
        Initializes a PressureSensor object from a configuration dictionary.
        
        Args:
            config: The target configuration dict.
        """
        try:
            id = config['id']
            name = config['name']
            min_voltage = config['voltage_range']['min']
            max_voltage = config['voltage_range']['max']
            min_pressure = config['pressure_range']['min']
            max_pressure = config['pressure_range']['max']
        except KeyError as e:
            raise ValueError(f"Pressure sensor config missing key: {e}")
                 
        return cls(
            id = id,
            name = name,
            min_voltage = min_voltage,
            max_voltage = max_voltage,
            min_pressure = min_pressure,
            max_pressure = max_pressure
        )

    @property
    def id(self) -> int:
        """
        Unique ID of this pressure sensor.
        """
        return self._id
        
    @property
    def min_voltage(self) -> float:
        """
        Minimum voltage output of this pressure sensor.
        """
        return self._min_voltage
    
    @property
    def max_voltage(self) -> float:
        """
        Maximum voltage output of this pressure sensor.
        """
        return self._max_voltage
    
    @property
    def min_pressure(self) -> float:
        """
        Minimum pressure measurable by this pressure sensor.
        """
        return self._min_pressure
    
    @property
    def max_pressure(self) -> float:
        """
        Maximum pressure measurable by this pressure sensor.
        """
        return self._max_pressure
    
    @property
    def pressure(self) -> float:
        """
        Current pressure read by sensor.
        """
        voltage = AnalogIn(self._adc, self._channel).voltage
        voltage_scale = self._max_voltage - self._min_voltage
        pressure_scale = self._max_pressure - self._min_pressure
        return ((voltage - self._min_voltage) * (pressure_scale / voltage_scale)) + self._min_pressure