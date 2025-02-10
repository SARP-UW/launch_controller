import sys, os
sys.path.append(os.getcwd()[0:os.getcwd().find('/GSE') + 4] + '/launch_controller')
from data_codec import DataCodec
from utils import load_config

# f = float
# h = short
# ? = boolean
# i = int

class TestDataCodec():
	def setup_method(self):
		gse_master = load_config()
		self.prop_or_fill = gse_master['control_key']

		print(f'{self.prop_or_fill} schema')

		self.command_codec = DataCodec('command')
		self.telemetry_codec = DataCodec("telemetry")

	def teardown_method(self):
		print()


# TESTING __INIT__()
	def test_command_initialization(self):
		# Test if the schema is loaded correctly
		expected_schema = {}
		if self.prop_or_fill == 'prop':
			expected_schema = {
				"pc_state": "h",
				"pc_soft_armed": "?",
				"pc_fire": "?",
				"pc_redlines_armed": "?",
				"pc_pulse": "i",
				"pc_pdelay": "i"
        	}
		elif self.prop_or_fill == 'fill':
			expected_schema = {
				"fc_state": "h",
				"fc_soft_armed": "?",
				"fc_redlines_armed": "?",
				"fc_pulse": "i",
				"fc_pdelay": "i"
			}

		print(f'Command codec schema:\n{self.command_codec.msg_schema}')

		assert self.command_codec.msg_schema == expected_schema

	def test_telemetry_initialization(self):
		# Test if the schema is loaded correctly
		p_f = self.prop_or_fill[0]
		expected_schema = {
			f'{p_f}c_timestamp': "f",
			f'{p_f}c_cpu_temp': "f",
			f'{p_f}c_hard_armed': "?",
			f'{p_f}c_soft_armed': "?",
			f'{p_f}c_redlines_armed': "?",
			f'{p_f}c_state': "h",
			f'{p_f}c_scr_tag': "h",
			f'{p_f}c_adc1_c1': "f",
			f'{p_f}c_adc1_c2': "f",
			f'{p_f}c_adc1_c3': "f",
			f'{p_f}c_adc1_c4': "f",
			f'{p_f}c_adc2_c1': "f",
			f'{p_f}c_adc2_c2': "f",
			f'{p_f}c_adc2_c3': "f",
			f'{p_f}c_adc2_c4': "f"
		}

		print(f'Telemetry codec schema:\n{self.telemetry_codec.msg_schema}')

		assert self.telemetry_codec.msg_schema == expected_schema

# TESTING ENCODE AND DECODE
	def test_command_encode_decode(self):
        # Test encoding and decoding
		p_f = self.prop_or_fill[0]
		test_msg = {}

		if self.prop_or_fill == 'prop':
			test_msg = {
				"pc_state": 1,
				"pc_soft_armed": False,
				"pc_fire": False,
				"pc_redlines_armed": False,
				"pc_pulse": 1,
				"pc_pdelay": 1
        	}
		elif self.prop_or_fill == 'fill':
			test_msg = {
				"fc_state": 1,
				"fc_soft_armed": False,
				"fc_redlines_armed": False,
				"fc_pulse": 1,
				"fc_pdelay": 1
			}

		encoded_packet = self.command_codec.encode(test_msg)
		decoded_msg = self.command_codec.decode(encoded_packet)

		print(f'Test message:\n{test_msg}\n')
		print(f'Encoded packet:\n{encoded_packet}\n')
		print(f'Decoded message:\n{decoded_msg}')

		# Check if the decoded message matches the original message
		assert test_msg[f'{p_f}c_state'] == decoded_msg[f'{p_f}c_state']
		assert test_msg[f'{p_f}c_soft_armed'] == decoded_msg[f'{p_f}c_soft_armed']
		if self.prop_or_fill == 'prop': assert test_msg['pc_fire'] == decoded_msg['pc_fire']
		assert test_msg[f'{p_f}c_redlines_armed'] == decoded_msg[f'{p_f}c_redlines_armed']
		assert test_msg[f'{p_f}c_pulse'] == decoded_msg[f'{p_f}c_pulse']
		assert test_msg[f'{p_f}c_pdelay'] == decoded_msg[f'{p_f}c_pdelay']

	def test_telemetry_encode_decode(self):
        # Test encoding and decoding
		p_f = self.prop_or_fill[0]
		test_msg = {
			f'{p_f}c_timestamp': 1.0,
			f'{p_f}c_cpu_temp': 1.0,
			f'{p_f}c_hard_armed': False,
			f'{p_f}c_soft_armed': False,
			f'{p_f}c_redlines_armed': False,
			f'{p_f}c_state': 1,
			f'{p_f}c_scr_tag': 1,
			f'{p_f}c_adc1_c1': 1.0,
			f'{p_f}c_adc1_c2': 1.0,
			f'{p_f}c_adc1_c3': 1.0,
			f'{p_f}c_adc1_c4': 1.0,
			f'{p_f}c_adc2_c1': 1.0,
			f'{p_f}c_adc2_c2': 1.0,
			f'{p_f}c_adc2_c3': 1.0,
			f'{p_f}c_adc2_c4': 1.0
		}

		encoded_packet = self.telemetry_codec.encode(test_msg)
		decoded_msg = self.telemetry_codec.decode(encoded_packet)

		print(f'Test message:\n{test_msg}\n')
		print(f'Encoded packet:\n{encoded_packet}\n')
		print(f'Decoded message:\n{decoded_msg}')

		# Check if the decoded message matches the original message
		assert test_msg[f'{p_f}c_timestamp'] == decoded_msg[f'{p_f}c_timestamp']
		assert test_msg[f'{p_f}c_cpu_temp'] == decoded_msg[f'{p_f}c_cpu_temp']
		assert test_msg[f'{p_f}c_hard_armed'] == decoded_msg[f'{p_f}c_hard_armed']
		assert test_msg[f'{p_f}c_soft_armed'] == decoded_msg[f'{p_f}c_soft_armed']
		assert test_msg[f'{p_f}c_redlines_armed'] == decoded_msg[f'{p_f}c_redlines_armed']
		assert test_msg[f'{p_f}c_state'] == decoded_msg[f'{p_f}c_state']
		assert test_msg[f'{p_f}c_scr_tag'] == decoded_msg[f'{p_f}c_scr_tag']
		assert test_msg[f'{p_f}c_adc1_c1'] == decoded_msg[f'{p_f}c_adc1_c1']
		assert test_msg[f'{p_f}c_adc1_c2'] == decoded_msg[f'{p_f}c_adc1_c2']
		assert test_msg[f'{p_f}c_adc1_c3'] == decoded_msg[f'{p_f}c_adc1_c3']
		assert test_msg[f'{p_f}c_adc1_c4'] == decoded_msg[f'{p_f}c_adc1_c4']
		assert test_msg[f'{p_f}c_adc2_c1'] == decoded_msg[f'{p_f}c_adc2_c1']
		assert test_msg[f'{p_f}c_adc2_c2'] == decoded_msg[f'{p_f}c_adc2_c2']
		assert test_msg[f'{p_f}c_adc2_c3'] == decoded_msg[f'{p_f}c_adc2_c3']
		assert test_msg[f'{p_f}c_adc2_c4'] == decoded_msg[f'{p_f}c_adc2_c4']

# TESTING INVALID INPUTS
	def test_short_command_input(self):
        # Test encoding with missing keys
		p_f = self.prop_or_fill[0]

		test_msg = {
			f'{p_f}c_state': 1
		}

		try:
			print('Short command input:')
			self.command_codec.encode(test_msg)
		except (KeyError):
			print('\tKeyError thrown - test passed')
			assert True
		else:
			print('\tKeyError not thrown - test failed')
			assert False
		
	def test_short_telemetry_input(self):
		# Test encoding with missing keys
		p_f = self.prop_or_fill[0]

		test_msg = {
			f'{p_f}c_timestamp': 1.0
		}

		try:
			print('Short telemetry input:')
			self.telemetry_codec.encode(test_msg)
		except (KeyError):
			print('\tKeyError thrown - test passed')
			assert True
		else:
			print('\tKeyError not thrown - test failed')
			assert False