import sys, os
sys.path.append(os.path.dirname(os.getcwd()) + '/launch_controller')
from sensors import Sensors
from unittest.mock import MagicMock
import logging
logging.basicConfig(level=logging.DEBUG)

# Problem - sensors.py uses gpiozero library only available on RPi OS
# Solution - we use MagicMock as a means of simulating output from gpiozero and PROP_ADC_Driver
class TestSensors:
    """
    Test class for the sensors module
    
    run 'pytest -rA test_sensors.py' for detailed info on each test
    """

    def setup_method(self, method):
        """Initialize each test object to return these values for read_pressure and temperature"""

        print(f"Setting up {method}")

        # Create fake ADC drivers with fake return values for adc.read_pressure()
        adc1 = MagicMock()
        adc1.read_pressure = MagicMock(return_value=1)
        adc2 = MagicMock()
        adc2.read_pressure = MagicMock(return_value=2)
        self.fake_adc_drivers = [adc1, adc2]

        # Create fake cpu with a fake temperature
        fake_cpu_temp = MagicMock()
        fake_cpu_temp.temperature = 3

        self.sensor = Sensors("Placeholder???", self.fake_adc_drivers, fake_cpu_temp)

    def teardown_method(self, method):
        print(f"Tearing down {method}")


# TESTING GET_CPU_TEMP()

    def test_cpu_temp_is_zero_off_target(self):
        assert self.sensor.get_cpu_temp() == 0

    def test_cpu_temp_is_nonzero_on_target(self):
        self.sensor.ontarget = True
        assert self.sensor.get_cpu_temp() == 3


# TESTING GET_ADC_READINGS()

    def test_adc_readings_is_list(self):
        adc_readings = self.sensor.get_adc_readings()
        assert isinstance(adc_readings, list)


    def test_adc_readings_not_empty(self):
        num_adc_readings = len(self.sensor.get_adc_readings())
        assert num_adc_readings > 0


    def test_adc_readings_length_is_four_times_num_of_drivers(self):
        four_times_num_channels = len(self.fake_adc_drivers) * 4
        num_adc_readings = len(self.sensor.get_adc_readings())
        assert num_adc_readings == four_times_num_channels


    def test_adc_readings_is_all_zeros_off_target(self):
        self.sensor.ontarget = False
        adc_readings = self.sensor.get_adc_readings()
        assert adc_readings == [0, 0, 0, 0, 0, 0, 0, 0]


    def test_adc_readings_is_nonzero_list_on_target(self):
        self.sensor.ontarget = True
        adc_readings = self.sensor.get_adc_readings()
        assert adc_readings == [1, 1, 1, 1, 2, 2, 2, 2]


# TESTING GET_HARD_ARMED()

    def test_get_hard_armed_returns_false(self):
        hard_armed_state = self.sensor.get_hard_armed()
        assert hard_armed_state == False


# TESTING GET_TELEMETRY()

    def test_telemetry_is_dictionary(self):
        telemetry = self.sensor.get_telemetry()
        assert isinstance(telemetry, dict)


    def test_telemetry_cpu_temp_is_zero_off_target(self):
        self.sensor.ontarget = False
        telemetry = self.sensor.get_telemetry()

        keys = list(telemetry)
        cpu_temperature = telemetry[keys[0]]
        assert cpu_temperature == 0

    
    def test_telemetry_pressures_are_zero_off_target(self):
        self.sensor.ontarget = False
        telemetry = self.sensor.get_telemetry()

        keys = list(telemetry)
        
        for key in keys[1:-1]:
            pressure_reading = telemetry[key]
            assert pressure_reading == 0


    def test_telemetry_hard_armed_state_is_false(self):
        self.sensor.ontarget = False
        telemetry = self.sensor.get_telemetry()

        keys = list(telemetry)

        hard_armed_state = telemetry[keys[-1]]
        assert hard_armed_state == False

# TODO - DIFFERENTIATE BETWEEN FILL AND PROP TESTS
# TODO - CREATE MECHANISM TO SET FILL AND PROP STATE FOR SENSORS