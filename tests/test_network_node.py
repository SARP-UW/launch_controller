import sys, os
sys.path.append(os.getcwd()[0:os.getcwd().find('/GSE') + 4] + '/launch_controller')
from network_node import SendNode, ReceiveNode
from telem_codec import TelemCodec
from command_codec import CommandCodec

TLM_SERVER_ADDR_IP = ""
TLM_SERVER_ADDR_PORT = 31000
CMD_RECEIVER_ADDR_IP = ""
CMD_RECEIVER_ADDR_PORT = 31002
GC_ADDR_IP = "10.0.0.100"
GC_ADDR_PORT = 31000

class TestNetworkNode:
	def setup_method(self, method):
		print(f"Setting up {method}")

		self.send_node = SendNode((TLM_SERVER_ADDR_IP, TLM_SERVER_ADDR_PORT), (GC_ADDR_IP, GC_ADDR_PORT), TelemCodec())
		self.recieve_node = ReceiveNode((CMD_RECEIVER_ADDR_IP, CMD_RECEIVER_ADDR_PORT), CommandCodec())

	def teardown_method(self, method):
		print(f"Tearing down {method}")


# TESTING __INIT__()
	def test_initialization(self):
		assert True

# TESTING SEND_NODE.SHUTDOWN(SELF)



# TESTING SEND_NODE.SEND(SELF, MSG)



# TESTING RECEIVE_NODE.SHUTDOWN(SELF)



# TESTING RECEIVE_NODE.RECEIVE(SELF)