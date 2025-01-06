import sys, os
sys.path.append(os.path.dirname(os.getcwd()) + '/launch_controller')
from relays import Relays
from unittest.mock import MagicMock

class TestSensors:
	def setup_method(self, method):
		print(f"Setting up {method}")
        
		gpio = MagicMock()
		self.relays = Relays(gpio, os.path.dirname(os.getcwd()) + '/launch_controller/gse_master.json')

	def teardown_method(self, method):
		print(f"Tearing down {method}")


# TESTING __INIT__()
	def test_initialization(self):
		assert True