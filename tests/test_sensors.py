import sys, os
sys.path.append(os.path.dirname(os.getcwd()) + '/launch_controller')
from sensors import Sensors
import logging
import pytest
logging.basicConfig(level=logging.DEBUG)

# sensors.py uses gpiozero library only available on RPi OS
class TestSensors:
    """
    Test class for the sensors module
    
    run 'pytest -rA test_sensors.py' for detailed info on each test
    """

    def setup_method(self, method):
        print(f"Setting up {method}")
        self.sensor = Sensors("placeholder")

    def teardown_method(self, method):
        print(f"Tearing down {method}")

    def test_get_cpu_temp(self):
        assert self.sensor.get_cpu_temp() == 0