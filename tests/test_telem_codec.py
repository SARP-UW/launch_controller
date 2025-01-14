import sys, os
sys.path.append(os.getcwd()[0:os.getcwd().find('/GSE') + 4] + '/launch_controller')
import unittest
from unittest.mock import patch, mock_open
import json
from telem_codec import TelemCodec  


class TestTelemCodec(unittest.TestCase):

    def setUp(self):
        # Sample control data to mock
        # self.control_data = 'p'  # Mocked control key
        
        # Sample telemetry schema for mocking
        self.telemetry_schema = {
            "control_key": "prop",
            "telemetry_config": {
                "p": {
                    "temperature": "f",
                    "humidity": "h",
                    "adc_channels": {
                        "channel1": "h",
                        "channel2": "h"
                    }
                }
            }
        }

        # Use mock_open to simulate file reading
        # self.patcher_control = patch("builtins.open", mock_open(read_data=self.control_data))
        self.patcher_schema = patch("builtins.open", mock_open(read_data=json.dumps(self.telemetry_schema)))

        # self.mock_control_file = self.patcher_control.start()
        self.mock_schema_file = self.patcher_schema.start()

        # Create an instance of TelemCodec
        self.codec = TelemCodec()


    def tearDown(self):
        # Stop patching
        # self.patcher_control.stop()
        self.patcher_schema.stop()

    def test_initialization(self):
        # Test if the schema is loaded correctly
        expected_schema = {
            'temperature': 'f',
            'humidity': 'h',
            'channel1': 'h',
            'channel2': 'h'
        }
        self.assertEqual(self.codec.msg_schema, expected_schema)

    def test_encode_decode(self):
        # Test encoding and decoding
        original_msg = {
            'temperature': 25.5,
            'humidity': 60,
            'channel1': 1024,
            'channel2': 2048
        }
        
        encoded_packet = self.codec.encode(original_msg)
        decoded_msg = self.codec.decode(encoded_packet)

        # Check if the decoded message matches the original message
        self.assertEqual(original_msg['temperature'], decoded_msg['temperature'])
        self.assertEqual(original_msg['humidity'], decoded_msg['humidity'])
        self.assertEqual(original_msg['channel1'], decoded_msg['channel1'])
        self.assertEqual(original_msg['channel2'], decoded_msg['channel2'])

    def test_invalid_input(self):
        # Test encoding with missing keys
        with self.assertRaises(KeyError):
            self.codec.encode({'temperature': 25.5})  # Missing 'humidity' and 'adc_channels'

if __name__ == '__main__':
    unittest.main()
