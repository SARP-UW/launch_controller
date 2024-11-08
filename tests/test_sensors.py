import sys, os
sys.path.append(os.path.join(os.path.dirname(sys.path[0]), ''))
from sensors import Sensors
import logging
import pytest
logging.basicConfig(level=logging.DEBUG)

# sensors.py uses gpiozero library only available on RPi OS
class TestSensors:
    @pytest.fixture
    def get_sensor(self):
        self.sensor = Sensors()

    def test_sensor(self, get_sensor):
        sensor1 = get_sensor
        assert(sensor1.get_cpu_temp() >= 0)
