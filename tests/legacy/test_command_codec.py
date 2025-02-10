import sys, os
sys.path.append(os.getcwd()[0:os.getcwd().find('/GSE') + 4] + '/launch_controller')
# from command_codec import CommandCodec
from data_codec import DataCodec

class TestCommandCodec:
	def setup_method(self, method):
		print(f"Setting up {method}")
        
		self.command_codec = DataCodec('command')

	def teardown_method(self, method):
		print(f"Tearing down {method}")


# TESTING __INIT__()
	def test_initialization(self):
		# Test if the schema is loaded correctly
		expected_schema = {
			'pc_state': 'h',
			'pc_soft_armed': '?',
			'pc_fire': '?',
			'pc_redlines_armed': '?',
			'pc_pulse': 'i',
			'pc_pdelay': 'i'
		}

		assert self.command_codec.msg_schema == expected_schema

	def test_encode_decode(self):
        # Test encoding and decoding
		test_msg = {
			"pc_state": 1,
			"pc_soft_armed": False,
			"pc_fire": False,
			"pc_redlines_armed": False,
			"pc_pulse": 1,
			"pc_pdelay": 1
		}
        
		encoded_packet = self.command_codec.encode(test_msg)
		decoded_msg = self.command_codec.decode(encoded_packet)

		# Check if the decoded message matches the original message
		assert test_msg['pc_state'] == decoded_msg['pc_state']
		assert test_msg['pc_soft_armed'] == decoded_msg['pc_soft_armed']
		assert test_msg['pc_fire'] == decoded_msg['pc_fire']
		assert test_msg['pc_redlines_armed'] == decoded_msg['pc_redlines_armed']
		assert test_msg['pc_pulse'] == decoded_msg['pc_pulse']
		assert test_msg['pc_pdelay'] == decoded_msg['pc_pdelay']

	def test_invalid_input(self):
        # Test encoding with missing keys
		test_msg = {
			"pc_state": 1
		}

		try:
			self.command_codec.encode(test_msg)
		except (KeyError):
			assert True
		else:
			assert False
		