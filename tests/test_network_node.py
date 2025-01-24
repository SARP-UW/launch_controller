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

TELEM_TEST_MSG = {
	"pc_timestamp": 1.0,
	"pc_cpu_temp": 1.0,
	"pc_hard_armed": False,
	"pc_soft_armed": False,
	"pc_redlines_armed": False,
	"pc_state": 1,
	"pc_scr_tag": 1,
	"pc_adc1_c1": 1.0,
	"pc_adc1_c2": 1.0,
	"pc_adc1_c3": 1.0,
	"pc_adc1_c4": 1.0,
	"pc_adc2_c1": 1.0,
	"pc_adc2_c2": 1.0,
	"pc_adc2_c3": 1.0,
	"pc_adc2_c4": 1.0
}

# NOTE: not yet used, but could be used for testing receive_node.receive()
COMM_TEST_MSG = {
	"pc_state": 1,
	"pc_soft_armed": False,
	"pc_fire": False,
	"pc_redlines_armed": False,
	"pc_pulse": 1,
	"pc_pdelay": 1
}

class TestNetworkNode:
	def setup_method(self):
		# print(f"Setting up {method}")
		print("Initializing send/receive nodes")

		self.send_node = SendNode((TLM_SERVER_ADDR_IP, TLM_SERVER_ADDR_PORT), (GC_ADDR_IP, GC_ADDR_PORT), TelemCodec())
		self.receive_node = ReceiveNode((CMD_RECEIVER_ADDR_IP, CMD_RECEIVER_ADDR_PORT), CommandCodec())

	def teardown_method(self):
		# print(f"Tearing down {method}")
		print("Shutting down send/receive nodes")

		self.send_node.shutdown()
		self.receive_node.shutdown()


# TESTING __INIT__()
	def test_initialization(self):
		assert True

# TESTING SEND_NODE.SHUTDOWN()
	def test_send_node_shutdown(self):
		self.send_node.shutdown()

		assert True


# TESTING SEND_NODE.SEND(MSG)
	def test_send_node_send(self):
		self.send_node.send(TELEM_TEST_MSG)
				
		assert True


# TESTING RECEIVE_NODE.SHUTDOWN()
	def test_receive_node_shutdown(self):
		self.receive_node.shutdown()

		assert True


# TESTING RECEIVE_NODE.RECEIVE()
	def test_receive_node_receive(self):
		
		# TODO: figure out how to mock data to receive

		assert False