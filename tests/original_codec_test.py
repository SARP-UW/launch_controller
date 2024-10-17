from codec import Codec
import unittest

class TestCodec(unittest.TestCase):
    def setUp(self):
        self.msg_schema = {
            'temperature': 'f',  # Float
            'humidity': 'h'      # Short
        }
        self.codec = Codec(self.msg_schema)
    
    def test_encode_decode(self):
        original_msg = {
            'temperature': 25.5,
            'humidity': 60
        }

        encoded_packet = self.codec.encode(original_msg)
        print(encoded_packet)
        decoded_msg = self.codec.decode(encoded_packet)
        print(decoded_msg)

        self.assertEqual(original_msg['temperature'], decoded_msg['temperature'])
        self.assertEqual(original_msg['humidity'], decoded_msg['humidity'])

    def test_encode_produces_correct_bytes(self):
        original_msg = {
            'temperature': 25.5,
            'humidity': 60
        }
        
        expected_packet = self.codec.encode(original_msg)
        
        expected_msg_vals = (25.5, 60)
        expected_bytes = self.codec.struct.pack(*expected_msg_vals)
        
        self.assertEqual(expected_packet, expected_bytes)

    def test_invalid_input(self):

        with self.assertRaises(KeyError):
            self.codec.encode({'temperature': 25.5})  # Missing 'humidity'
        
        # with self.assertRaises(TypeError):
        #     self.codec.decode(b'Invalid bytes')  # Invalid byte string

if __name__ == '__main__':
    unittest.main()