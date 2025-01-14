import sys, os
sys.path.append(os.getcwd()[0:os.getcwd().find('/GSE') + 4] + '/launch_controller')
from command_codec import CommandCodec

class TestCommandCodec:
	def setup_method(self, method):
		print(f"Setting up {method}")
        
		self.command_codec = CommandCodec()

	def teardown_method(self, method):
		print(f"Tearing down {method}")


# TESTING __INIT__()
	def test_initialization(self):
		assert True