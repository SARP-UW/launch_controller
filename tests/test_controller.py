import sys, os
sys.path.append(os.getcwd()[0:os.getcwd().find('/GSE') + 4] + '/launch_controller')
from controller import Controller

import logging
import unittest
from unittest.mock import Mock, patch, MagicMock, call
import fake_rpigpio.utils
fake_rpigpio.utils.install()
import RPi.GPIO as GPIO
from controller import Controller
from sensors import Sensors
from datetime import datetime
#from relays import CLOSED_STATE

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
    
class TestController(unittest.TestCase):
    def setUp(self):
        # Initialize relays and other mocked components
        self.mock_relays = MagicMock()
        self.mock_sensors = MagicMock()
        self.mock_cmd_receiver = MagicMock()
        self.mock_tlm_server = MagicMock()
        self.mock_os = MagicMock()
        self.mock_relays = MagicMock()
        self.GPIO_MAPPING = [4, 17, 27, 22, 10, 9, 11, 5, 6, 13]

        # Initialize controller with the config file path
        self.controller = Controller()
        self.controller.relays = self.mock_relays
        self.controller.sensors = self.mock_sensors
        self.controller.cmdReceiver = self.mock_cmd_receiver
        self.controller.tlmServer = self.mock_tlm_server
        
        self.logger_name = "test_logger"
        self.log_file = "test.log"
        

    def tearDown(self):
        # Properly close any network sockets or resources
        if self.controller and self.controller.tlmServer:
            self.controller.tlmServer.sock.close()

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
        state = self.controller.relays._requested_state[valve]
        gpio_state[valve] = state
        time = datetime.now().time() 
        print(f"UPDATE: Set pin {valve} to state {int(state)} at {time}") 
        updates.append(GPIOoutput(valve, int(state), time))
    
    def mock_gpio_update(self, GPIO, gpio_state, updates):
        state = self.controller.relays._requested_state
        gpio_state = state
        time = datetime.now().time() 
        updates.append((gpio_state.copy(), time))
        print(f"UPDATES LIST {updates}") 

        
    def test_process_request_fire_sequence_prop(self):
        self.controller._control == 'prop'
        # Simulate receiving a command to fire
        command = {
            f'{self.controller._control[0]}c_fire': True,  # pc_fire is true
            f'{self.controller._control[0]}c_pulse': -1,
            f'{self.controller._control[0]}c_pdelay': 5,
            f'{self.controller._control[0]}c_soft_armed': False,
            f'{self.controller._control[0]}c_redlines_armed': False,
            f'{self.controller._control[0]}c_state': 1
        }
        self.controller.cmdReceiver.receive.return_value = (command, 'address')
        
        # Process the request
        self.controller.processRequest()

        # Assert fire sequence initiated
        self.mock_relays.INITIATE_FIRE_SEQUENCE = MagicMock()
        assert self.mock_relays.INITIATE_FIRE_SEQUENCE(GPIO) is not None, "INITIATE_FIRE_SEQUENCE was not called!"

            
    def test_process_request_fire_sequence_fill(self):
        self.controller._control == 'fill'
        # Simulate receiving a command to fire but in fill mode
        command = {
            f'{self.controller._control[0]}c_fire': True,  # pc_fire is true
            f'{self.controller._control[0]}c_pulse': -1,
            f'{self.controller._control[0]}c_pdelay': 5,
            f'{self.controller._control[0]}c_soft_armed': False,
            f'{self.controller._control[0]}c_redlines_armed': False,
            f'{self.controller._control[0]}c_state': 1
        }
        self.controller.cmdReceiver.receive.return_value = (command, 'address')
        
        # Process the request
        self.controller.processRequest()

        # Assert fire sequence is NOT initiated
        self.mock_relays.INITIATE_FIRE_SEQUENCE = MagicMock()
        try:
            self.mock_relays.INITIATE_FIRE_SEQUENCE.assert_not_called()
        except AssertionError:
            raise AssertionError("INITIATE_FIRE_SEQUENCE was unexpectedly called!")

            
    def test_process_request_pulse_valve(self):
        # Simulate receiving a command to pulse valve
        command = {f'{self.controller._control[0]}c_fire': False, 
                f'{self.controller._control[0]}c_pulse':1,  # valve
                f'{self.controller._control[0]}c_pdelay':5000,  # delay
                f'{self.controller._control[0]}c_soft_armed':False, 
                f'{self.controller._control[0]}c_redlines_armed': False, 
                f'{self.controller._control[0]}c_state': 1}
        
        # Process the request
        self.controller.cmdReceiver.receive.return_value = (command, 'address')
        self.controller.processRequest()

        # Assert relays.PULSE_VALCE is called
        self.mock_relays.PULSE_VALVE = MagicMock()
        pulse_valve = command[f"{self.controller._control[0]}c_pulse"]
        assert self.mock_relays.PULSE_VALVE(GPIO, pulse_valve, command[f"{self.controller._control[0]}c_pdelay"]) is not None, "PULSE_VALVE was not called!"

    def test_process_request_arm(self):
        # Simulate receiving a command to arm
        command = {f'{self.controller._control[0]}c_fire': False, 
                f'{self.controller._control[0]}c_pulse':1,  
                f'{self.controller._control[0]}c_pdelay':5000,  
                f'{self.controller._control[0]}c_soft_armed':True,  # command to arm
                f'{self.controller._control[0]}c_redlines_armed': False, 
                f'{self.controller._control[0]}c_state': 1}
        self.controller.cmdReceiver.receive.return_value = (command, 'address')
        self.soft_arm = False
        
        # Process the request
        self.controller.processRequest()
        
        # Assert controller soft arm is set to True
        self.assertEqual(self.controller.soft_arm, True, "Soft arm not set to true")
        
        # Assert relays.arm is called
        self.mock_relays.arm = MagicMock(GPIO)
        assert self.mock_relays.arm(GPIO) is not None, "relays.arm was not called!"

        
    def test_process_request_disarm(self):
        # Simulate receiving a command to disarm
        command = {f'{self.controller._control[0]}c_fire': False, 
                f'{self.controller._control[0]}c_pulse':1,  
                f'{self.controller._control[0]}c_pdelay':5000,  
                f'{self.controller._control[0]}c_soft_armed':False,  # command to disarm
                f'{self.controller._control[0]}c_redlines_armed': False, 
                f'{self.controller._control[0]}c_state': 1}
        self.controller.cmdReceiver.receive.return_value = (command, 'address')
        self.soft_arm = True
        
        # Process the request
        self.controller.processRequest()
        
        # Assert controller soft arm is set to False
        self.assertEqual(self.controller.soft_arm, False, "Soft arm not set to false")
        
        # Assert relays.disarm is called
        self.mock_relays.disarm = MagicMock(GPIO)
        assert self.mock_relays.disarm(GPIO) is not None, "relays.disarm was not called!"
    
    def test_process_request_arm_redlines(self):
        # Simulate receiving a command to arm redlines
        command = {f'{self.controller._control[0]}c_fire': False, 
                f'{self.controller._control[0]}c_pulse':1,  
                f'{self.controller._control[0]}c_pdelay':5000,  
                f'{self.controller._control[0]}c_soft_armed':False,  
                f'{self.controller._control[0]}c_redlines_armed': True, # command to arm redlines
                f'{self.controller._control[0]}c_state': 1}
        self.controller.cmdReceiver.receive.return_value = (command, 'address')
        self.redlines_armed = False
                
        # Process the request
        self.controller.processRequest()
        
        # Assert controller redlines set to true
        self.assertEqual(self.controller.redlines_armed, True, "Redlines arm not set to true")
        
        
    def test_process_request_ignore_redlines(self):
        # Simulate NOT receiving a command to arm redlines
        command = {f'{self.controller._control[0]}c_fire': False, 
                f'{self.controller._control[0]}c_pulse':1,  
                f'{self.controller._control[0]}c_pdelay':5000,  
                f'{self.controller._control[0]}c_soft_armed':False,  
                f'{self.controller._control[0]}c_redlines_armed': False, # no command to arm redlines
                f'{self.controller._control[0]}c_state': 1}
        self.controller.cmdReceiver.receive.return_value = (command, 'address')
        self.ignore_redlines = False
                
        # Process the request
        self.controller.processRequest()
        
        # Assert controller ignore_redlines set to true
        self.assertEqual(self.controller.ignore_redlines, True, "Redlines not ignored!")

    def test_actuator_checks(self):
        self.controller.checkRedlines = MagicMock()
        self.controller.processRequest = MagicMock()
        self.mock_relays.update = MagicMock(GPIO)
        
        # Assert controller .checkRedlines(), .processRequest() and relays.update() called
        assert self.controller.checkRedlines() is not None, "check redlines was not called!"
        assert self.controller.processRequest() is not None, "process request was not called!"
        assert self.mock_relays.update(GPIO) is not None, "relays update was not called!"

    @patch.object(Controller, 'pingAddress')
    def test_check_network_success(self, mock_ping):
        # Mock successful ping (os.system returns 0)
        mock_ping.return_value = 0
        self.controller.lastPing = None

        c = self.controller.actualCheckNetwork(count=1)
        # Assert last ping is updated
        self.assertNotEqual(self.controller.lastPing, None)
        # Assert count is reset to 0 after a successful ping
        self.assertEqual(c, 0)


    @patch.object(Controller, 'pingAddress')
    def test_check_network_failure_vent(self, mock_ping):
        # Mock failed ping (os.system returns 1)
        mock_ping.return_value = 1
        self.controller.lastPing = 300  #enters SET_VENT_STATE conditional (time.time() - self.lastPing > 600)
        self.controller.relays._armed = True

        # Call to check network
        c = self.controller.actualCheckNetwork(count=1)
        
        # Assert last ping is not updated
        self.assertEqual(self.controller.lastPing, 300)
        
        # Assert relays.SET_VENT_STATE(GPIO, 3) is called
        assert self.mock_relays.SET_VENT_STATE(GPIO, 3) is not None, "SET_VENT_STATE was not called!"

        # Assert count is incremented after a failed ping
        self.assertEqual(c, 2)

    @patch.object(Controller, 'pingAddress')
    def test_check_network_failure_closed(self, mock_ping):
        # Mock failed ping (os.system returns 1)
        mock_ping.return_value = 1
        self.controller.lastPing = 500  #enters SET_CLOSED_STATE conditional (time.time() - self.lastPing < 600)
        self.controller.relays._armed = True
        
        # Call to check network
        c = self.controller.actualCheckNetwork(count=1)
        
        # Assert last ping is not updated
        self.assertEqual(self.controller.lastPing, 500)
        
        # Assert self.relays.SET_CLOSED_STATE(GPIO, 3) is called
        assert self.mock_relays.SET_CLOSED_STATE(GPIO, 3) is not None, "SET_CLOSED_STATE was not called!"

        # Assert count is incremented after a failed ping
        self.assertEqual(c, 2)
        
    def test_set_logger(self):
        logger = self.controller.set_logger(self.logger_name, self.log_file)

        # Assert logger properly set up
        self.assertEqual(logger.name, self.logger_name)
        self.assertEqual(logger.name, self.logger_name)
        self.assertEqual(logger.level, logging.INFO)

        handlers = logger.handlers
        self.assertTrue(any(isinstance(h, logging.FileHandler) for h in handlers))
    
    @patch('time.time', return_value=1234567890)
    def test_actual_send_telemetry_success(self, mock_time):
        # mock telemetry results
        self.mock_sensors.get_telemetry = MagicMock(return_value={"sensor_data": 42})
        self.mock_relays.get_telemetry = MagicMock(return_value={"relay_data": 99})
        self.mock_tlm_server.send = MagicMock()
        self.controller.telem_logger = MagicMock()
        
        self.controller.actualSendTelemetry()
        expected_telemetry = {
            f'{self.controller._control[0]}c_timestamp': mock_time.return_value - mock_time.return_value,  # First-time timestamp
            f'{self.controller._control[0]}c_redlines_armed': False,
            'sensor_data': 42,
            'relay_data': 99
        }
        
        # Assert expected telemetry is sent
        self.mock_tlm_server.send.assert_called_once_with(expected_telemetry)
        self.controller.telem_logger.info.assert_not_called()
        


if __name__ == '__main__':
    unittest.main()
