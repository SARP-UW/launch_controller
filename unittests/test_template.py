#!/usr/bin/python

#-----------------------------------------------------------------
# Pytest detects tests in files, classes, and methods with specific syntax where test precedes all names
# File: test_something.py
# Class: TestSomething
# Method: test_something()
#-----------------------------------------------------------------

import sys, os
# Since unit tests are in another directory separate from main files, need to allow import of those files
# By default, adds project directory when path is empty e.g. SARP_UW/fillcontroller/
#                                   Add path of files here ↓
sys.path.append(os.path.join(os.path.dirname(sys.path[0]), ''))
import pytest
from something import Sensor
# import <other-packages>


# This will be recognized by Pytest
def test_something():
    pass


# This will also be recognized
class TestSomething:

    # Example fixture
    # a fixture will allow the test to automatically generate instances of another class or method being tested
    @pytest.fixture
    def get_sensor(self):
        self.sensor = Sensor()  # imported class

    # Example test case 
    # uses the fixture above to automatically generate a sensor instance which is used to run through test cases
    def test_sensor(self, get_sensor):
        assert(get_sensor.get_temp() >= 0)
        assert(get_sensor.get_temp() < 50)
        try:
            sensor.set_temp(10000)
        except:
            print("Extreme temperature fault")

    # Example parameterization
    # allows a test case to be run with a variety of inputs
    @pytest.mark.parameterize(
        "sensor,index",
        [
            (Sensor(), 1),
            (Sensor(), 2),
            (Sensor(), 3)
        ]
    )
    def test_sensors(self, sensor):
        assert(sensor.get_temp() != 0)
