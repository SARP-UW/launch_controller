import sys, os
sys.path.append(os.getcwd()[0:os.getcwd().find('/GSE') + 4] + '/launch_controller')
from utils import get_config_path, num

import logging
import unittest
from unittest.mock import Mock, patch, MagicMock, call
import fake_rpigpio.utils

fake_rpigpio.utils.install()
import RPi.GPIO as GPIO
from relays import Relays
from datetime import datetime

class GPIOoutput():
    def __init__(self, pin, state, time):
        self.pin = pin
        self.state = state
        self.time = time
    
    def __str__(self):
        return f"{self.pin} {self.state}"
    
    def get_pin(self):
        return self.pin
    
    def get_state(self):
        return self.state
    
    def get_time(self):
        return self.time
    
class TestRelays(unittest.TestCase):
    def setUp(self):
        # Initialize relays and other mocked components
        self.mock_sensors = MagicMock()
        self.mock_cmd_receiver = MagicMock()
        self.mock_tlm_server = MagicMock()
        self.mock_os = MagicMock()
        self.GPIO_MAPPING = [4, 17, 27, 22, 10, 9, 11, 5, 6, 13]

        self.relays = Relays(GPIO, get_config_path())
        self.relays.sensors = self.mock_sensors
        

    def tearDown(self):
        pass

    def time_difference(self, obj1, obj2):
        # Convert the time attributes to datetime objects for easy comparison
        time_format = "%H:%M:%S.%f"
        time1 = datetime.strptime(obj1.get_time().strftime(time_format), time_format)
        time2 = datetime.strptime(obj2.get_time().strftime(time_format), time_format)
        
        # Calculate the difference
        return abs((time2 - time1).total_seconds())

    def is_not_within_range(self, number, target, tolerance): 
        return abs(number - target) > tolerance

    def time_to_seconds(self, t):
        return t.hour * 3600 + t.minute * 60 + t.second + t.microsecond / 1e6

    def mock_gpio_output(self, pin, state, gpio_state, outputs):
        gpio_state[pin] = state
        time = datetime.now().time()
        print(f"Set pin {pin} to state {state} at {time}")
        outputs.append(GPIOoutput(pin, state, time))
    
    def mock_gpio_update_valve(self, GPIO, valve, gpio_state, updates): 
        state = self.relays._requested_state[valve]
        gpio_state[valve] = state
        time = datetime.now().time() 
        print(f"UPDATE: Set pin {valve} to state {int(state)} at {time}") 
        updates.append(GPIOoutput(valve, int(state), time))
    
    def mock_gpio_update(self, GPIO, gpio_state, updates):
        state = self.relays._requested_state
        gpio_state = state
        updates.append((gpio_state.copy()))
        print(f"UPDATES LIST {updates}") 
    
    def mock_gpio_update_vent(self, GPIO, gpio_state, updates):
        state = self.relays._requested_state
        gpio_state = state
        time = datetime.now().time() 
        updates.append((gpio_state.copy(), time))
        print(f"UPDATES LIST {updates}") 

    def test_arm(self):
        self.relays.arm(GPIO)
        self.assertEqual(self.relays._armed, True, "relays should be armed")

    def test_is_armed(self):
        self.relays._armed = True
        returned = self.relays.is_armed()
        self.assertEqual(returned, True, "is_armed should return True")
        
        self.relays._armed = False
        returned = self.relays.is_armed()
        self.assertEqual(returned, False, "is_armed should return False")
    
    def test_request_state(self):
        REQUEST_STATE = [0, 0, 0, 0, 0, 1, 0, 1, 1, 0]      
        # Call to request_state
        self.relays.request_state(request=REQUEST_STATE, tag=3) 
                
        # Assert appropriately changed requested state and tag
        self.assertEqual(self.relays._requested_state, REQUEST_STATE, "requested_state was not set correctly.")
        self.assertEqual(self.relays._SCR_tag, 3, "SCR tag was not set correctly.")
    
    def test_get_state(self):
        EXPECTED_STATE = [0, 0, 0, 0, 0, 1, 0, 1, 1, 0]
        self.relays._state = EXPECTED_STATE
        returned = self.relays.get_state()
        self.assertEqual(returned, EXPECTED_STATE, "Did not get correct state.")

        
    def test_get_telemetry(self):
        self.relays.is_armed = lambda: True  # Mock is_armed method to always return True
        EXPECTED_STATE = [0, 0, 0, 0, 0, 1, 0, 1, 1, 0]
        self.relays._state = EXPECTED_STATE
        states = num(EXPECTED_STATE)
        self.relays._SCR_tag = 3

        expected_telemObject = {
            self.relays.config['telemetry_config'][self.relays._control[0]][self.relays._control[0] + 'c_soft_armed']: True,
            self.relays.config['telemetry_config'][self.relays._control[0]][self.relays._control[0] +'c_state']: states,
            self.relays.config['telemetry_config'][self.relays._control[0]][self.relays._control[0] +'c_scr_tag']: 3
        }
        
        returned = self.relays.get_telemetry()
        self.assertEqual(returned, expected_telemObject, "Did not get correct telem object.")
        
        
    def test_fire_sequence_armed(self):
        # Mock GPIO.output to track pin states
        gpio_state = {}
        outputs = []
        
        GPIO.output = lambda pin, state: self.mock_gpio_output(pin, state, gpio_state, outputs)    

        # Ensure the controller is armed
        self.relays._armed = True
        self.relays._inj = False

        # test fire sequence
        self.relays.INITIATE_FIRE_SEQUENCE(GPIO)

        # Check that fire sequence was triggered for prop
        if self.relays._control == 'prop':          
            # Verify ignitor output
            if outputs[0].get_pin() != self.GPIO_MAPPING[0] or outputs[0].get_state() != GPIO.HIGH:
              self.fail("Ignitor pin not set to HIGH")
            
            # Verify delay for ignition
            if self.is_not_within_range(self.time_difference(outputs[0],outputs[1]), 3.5, 1):
                self.fail(f"Delay for Ignition is not 3.5 is {self.time_difference(outputs[0],outputs[1])}")

            # Verify oxygen and fuel solenoid outputs
            if outputs[1].get_pin() != self.GPIO_MAPPING[5] or outputs[1].get_state() != GPIO.HIGH:
              self.fail("OX solenoid pin not set to HIGH")
              
            # Verify the delay for oxygen solenoid
            if self.is_not_within_range(self.time_difference(outputs[1],outputs[2]), 0.0055, 0.5):
                self.fail(f"Delay for Ignition is not 0.0055 is {self.time_difference(outputs[1],outputs[2])}")
            
            if outputs[2].get_pin() != self.GPIO_MAPPING[6] or outputs[2].get_state() != GPIO.HIGH:
              self.fail("Fuel solenoid pin not set to HIGH")
            
            # Verify pause for firing sequence duration
            if self.is_not_within_range(self.time_difference(outputs[2],outputs[3]), 8.5, 4):
                self.fail(f"Delay for Ignition is not 8.5 is {self.time_difference(outputs[2],outputs[3])}")
                
            # Check that solenoids are closed after 8.5 seconds
            self.assertEqual(gpio_state.get(self.GPIO_MAPPING[5]), GPIO.LOW, "OX solenoid pin not set to LOW")
            self.assertEqual(gpio_state.get(self.GPIO_MAPPING[6]), GPIO.LOW, "Fuel solenoid pin not set to LOW")
            # Check that ignitor is turned off after the sequence
            self.assertEqual(gpio_state.get(self.GPIO_MAPPING[0]), GPIO.LOW, "Ignitor pin not set to LOW")

        GPIO.output = GPIO.output
        
    
    def test_fire_sequence_inj(self):
        # Mock GPIO.output to track pin states
        gpio_state = {}
        outputs = []

        GPIO.output = lambda pin, state: self.mock_gpio_output(pin, state, gpio_state, outputs)
                
        # Ensure injection active
        self.relays._armed = False
        self.relays._inj = True

        # test fire sequence
        self.relays.INITIATE_FIRE_SEQUENCE(GPIO)

        # Check that fire sequence was triggered for prop        
        if self.relays._control == 'prop':          
            # Check that solenoids are closed
            self.assertEqual(gpio_state.get(self.GPIO_MAPPING[5]), GPIO.LOW, "OX solenoid pin not set to LOW")
            
            if self.is_not_within_range(self.time_difference(outputs[0],outputs[1]), 0.02, 0.5):
                self.fail(f"Delay for  shutoff is not 0.02 is {self.time_difference(outputs[0],outputs[1])}")
                
            self.assertEqual(gpio_state.get(self.GPIO_MAPPING[6]), GPIO.LOW, "Fuel solenoid pin not set to LOW")

            self.assertFalse(self.relays._inj, "The _inj attribute was not set to False")

        GPIO.output = GPIO.output

            
    def test_pulse_valve(self):
        # Mock GPIO.output to track pin states
        gpio_state = {}
        updates = []
        
        update_mock = Mock(side_effect=lambda GPIO: self.mock_gpio_update_valve(GPIO, valve, gpio_state, updates)) 
        self.relays.update = update_mock

        # original valve state before pulse
        valve = 1
        delay = 5
        initial_state = self.relays._requested_state[valve]
        
        self.relays.PULSE_VALVE(GPIO, valve=valve, delay=delay)
        
        self.assertEqual(len(updates), 2, f"Initial state {initial_state} Expected 2 output actions, but got a different number.")
                        
        # Check initial flip and update 
        if updates[0].get_pin() != valve or updates[0].get_state() == initial_state:  # should be flipped from initial state
            self.fail("Valve not flipped to be opposite")
        
        #check for appropriate delay
        if self.is_not_within_range(self.time_difference(updates[0], updates[1]), (delay / 1000), 0.1): 
            self.fail(f"Delay for valve pulse is not {(delay / 1000)} seconds, it is {self.time_difference(updates[0], updates[1])} seconds") 
        
        # Check final flip back and update
        if updates[1].get_pin() != valve or updates[1].get_state() != initial_state:  # should be flipped back to initial state
            self.fail("Valve not flipped to back to initial state")
        

    def test_disarm(self):
        # Set armed to start
        self.relays._armed = True
        self.relays._state =  [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]  # does not equal closed state

        self.assertNotEqual(self.relays._state, self.relays.get_closed_state(), "Relays were originally in CLOSED_STATE before disarm command")
        self.assertNotEqual(self.relays._armed, False, "Relays already set to disarmed before disarm command")

        # Process the request
        self.relays.disarm(GPIO)

        if self.relays._control == 'prop':          
            # Check that state is set to closed state
            self.assertEqual(self.relays._state, self.relays.get_closed_state(), "Relays were not set to CLOSED_STATE")
            self.assertEqual(self.relays._armed, False, "Relays not set to disarmed")
       

    @patch('time.time')
    def test_set_vent_state(self, mock_time):
        # Mock GPIO.output to track pin states
        gpio_state = []
        updates = []
        update_mock = Mock(side_effect=lambda GPIO: self.mock_gpio_update_vent(GPIO, gpio_state, updates)) 
        self.relays.update = update_mock
        
        if self.relays._control == "fill":
            EXPECTED_VENT_STATE = [0, 0, 0, 0, 0, 1, 0, 1, 1, 0]
        else:
            EXPECTED_VENT_STATE = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
            
      
        logging.info(f"Initial state: {self.relays.get_state()}")

        self.relays.SET_VENT_STATE(GPIO, tag=3)
        
        logging.info(f"Final state: {self.relays.get_state()}")
        
        # Assert self.relays.SET_VENT_STATE(GPIO, 3) appropriately changes relays
        self.assertEqual(self.relays._SCR_tag, 3, "SCR tag was not set correctly.")
        self.assertEqual(updates[0][0], EXPECTED_VENT_STATE, f"Requested state is not set to VENT_STATE (update 0)")
        
        # Verify 0.5 second delay
        time_diff = abs(self.time_to_seconds(updates[0][1]) - self.time_to_seconds(updates[1][1])) 
        if self.is_not_within_range(time_diff, 0.5, 1):
                self.fail(f"Delay for setting vent state is not 0.5 is {self.time_difference(updates[0][1],updates[1][1])}")
        
        EXPECTED_VENT_STATE[1] = not EXPECTED_VENT_STATE[1]
        self.assertEqual(updates[1][0], EXPECTED_VENT_STATE, "Requested state is not set to VENT_STATE (update 1)")


    def test_set_closed_state(self):
        # Mock GPIO.output to track pin states
        gpio_state = []
        updates = []
        update_mock = Mock(side_effect=lambda GPIO: self.mock_gpio_update(GPIO, gpio_state, updates)) 
        self.relays.update = update_mock
        
        if self.relays._control == "fill":
            EXPECTED_CLOSED_STATE = [0, 0, 0, 0, 1, 0, 1, 0, 0, 0]
        else:
            EXPECTED_CLOSED_STATE = [0, 0, 1, 0, 1, 0, 0, 0, 0, 0]        
        
        self.relays.SET_CLOSED_STATE(GPIO, tag=3)
        
        self.assertEqual(self.relays._SCR_tag, 3, "SCR tag was not set correctly.")
        self.assertEqual(updates[0], EXPECTED_CLOSED_STATE, f"Requested state is not set to EXPECTED_CLOSED_STATE (update 0).")

           
    def test_update(self):
        # Mock GPIO.output to track pin states
        gpio_state = {}
        outputs = []
        GPIO.output = lambda pin, state: self.mock_gpio_output(pin, state, gpio_state, outputs)

        # Case 1: Relays are armed, and the update is valid
        self.relays._armed = True
        self.relays._requested_state = [1, 0, 1, 0, 0, 1, 1, 0, 0, 1]
        self.relays._state = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

        # Mock check_safe_update to return a valid update
        self.relays.check_safe_update = MagicMock(return_value=(True, "Update is valid"))

        self.relays.update(GPIO)

        # Verify GPIO states and logs
        for idx, state in enumerate(self.relays._requested_state):
            expected_state = GPIO.HIGH if state == 1 else GPIO.LOW
            self.assertEqual(
                gpio_state.get(self.GPIO_MAPPING[idx]), expected_state, f"Pin {self.GPIO_MAPPING[idx]} state mismatch."
            )
        self.assertEqual(self.relays._state, self.relays._requested_state, "Relays state was not updated correctly.")

        # Case 2: Relays are armed, and the update is invalid
        self.relays._requested_state = [0, 1, 1, 0, 1, 1, 0, 0, 1, 0]
        self.relays.check_safe_update = MagicMock(return_value=(False, "Invalid state request"))

        self.relays.update(GPIO)

        # Ensure state was not updated
        self.assertEqual(self.relays._state, [1, 0, 1, 0, 0, 1, 1, 0, 0, 1], "Invalid update incorrectly changed state.")

        # Case 3: Relays are disarmed
        self.relays._armed = False
        self.relays._requested_state = [0, 0, 0, 0, 1, 1, 1, 0, 0, 1]

        self.relays.update(GPIO)

        # Ensure state was not updated
        self.assertEqual(self.relays._state, [1, 0, 1, 0, 0, 1, 1, 0, 0, 1], "State changed despite being disarmed.")
        self.assertEqual(self.relays._SCR_tag, 1, "SCR tag was not set correctly to 1")

        GPIO.output = GPIO.output  # Restore GPIO output
            
    def test_check_safe_update(self):
        # Case 1: No violations (prop mode - always return True)
        self.relays._control = "prop"
        result, message = self.relays.check_safe_update()
        self.assertTrue(result, "Did not automatically return True in prop mode")
        self.assertEqual(message, "")

        # Case 2: No violations in fill mode
        self.relays._control = "fill"
        self.relays._requested_state = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]   # No mutual exclusion or inclusion violations
        result, message = self.relays.check_safe_update()
        self.assertTrue(result, "Unexpected violation in valid fill state")
        self.assertEqual(message, "")

        # Case 3: Mutual exclusion violation
        self.relays._requested_state = [1, 1, 0, 0, 0, 0, 0, 0, 0, 0]  # BV-01 and BV-02 active
        result, message = self.relays.check_safe_update()
        self.assertFalse(result, "Failed to detect mutual exclusion violation for BV-01 and BV-02")
        self.assertIn("Mutual exclusion violation for BV-01 and BV-02", message)

        # Case 4: Mutual inclusion violation
        self.relays._requested_state = [0, 0, 0, 0, 1, 0, 0, 0, 0, 0]  # BV-05 active but BV-01 inactive
        result, message = self.relays.check_safe_update()
        self.assertFalse(result, "Failed to detect mutual inclusion violation for BV-05 and BV-01")
        self.assertIn("Mutual inclusion violation for BV-05 and BV-01", message)

        # Case 5: Another mutual inclusion violation
        self.relays._requested_state = [0, 0, 0, 0, 0, 0, 1, 0, 0, 0]  # BV-07 active but BV-03 inactive
        result, message = self.relays.check_safe_update()
        self.assertFalse(result, "Failed to detect mutual inclusion violation for BV-07 and BV-03")
        self.assertIn("Mutual inclusion violation for BV-07 and BV-03", message)

        # Case 6: Valid state in prop mode
        self.relays._control = "prop"
        result, message = self.relays.check_safe_update()
        self.assertTrue(result, "Unexpected failure in valid prop state")
        self.assertEqual(message, "")

if __name__ == '__main__':
    unittest.main()
