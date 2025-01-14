import sys, os
sys.path.append(os.getcwd()[0:os.getcwd().find('/GSE') + 4] + '/launch_controller')
from controller import Controller

class TestController:
	def setup_method(self, method):
		print(f"Setting up {method}")
        
		self.controller = Controller()

	def teardown_method(self, method):
		print(f"Tearing down {method}")


# TESTING __INIT__()
	def test_initialization(self):
		assert True