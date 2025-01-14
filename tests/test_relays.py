import sys, os
sys.path.append(os.getcwd()[0:os.getcwd().find('/GSE') + 4] + '/launch_controller')
from relays import Relays
from utils import get_config_path
from unittest.mock import MagicMock

class TestRelays:
	def setup_method(self, method):
		print(f"Setting up {method}")
        
		gpio = MagicMock()
		self.relays = Relays(gpio, get_config_path())

	def teardown_method(self, method):
		print(f"Tearing down {method}")


# TESTING __INIT__()
	def test_initialization(self):
		assert True