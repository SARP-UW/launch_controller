import sys, os
sys.path.append(os.getcwd()[0:os.getcwd().find('/GSE') + 4] + '/launch_controller')
from network_node import SendNode, ReceiveNode
from data_codec import DataCodec
import unittest
from unittest.mock import patch, MagicMock
import socket

class TestSendNode(unittest.TestCase):
  def setUp(self):
    self.mock_socket = patch('socket.socket').start()
    self.mock_sock_instance = self.mock_socket.return_value
    bind_addr = ('localhost', 12345)
    target_addr =  ('localhost', 54321)
    self.send_node = SendNode(bind_addr, target_addr, DataCodec(datatype="telemetry"))

  def tearDown(self):
    patch.stopall()

  def test_send_node_initialization(self):
    self.mock_socket.assert_called_once_with(socket.AF_INET, socket.SOCK_DGRAM)
    self.mock_sock_instance.bind.assert_called_once_with(('localhost', 12345))

  def test_send_node_send(self):
    mock_encode = MagicMock(return_value='encoded_data')
    self.send_node.codec.encode = mock_encode
    
    msg = {"pc_timestamp": 1.0}
    self.send_node.send(msg)
    
    mock_encode.assert_called_once_with(msg)
    self.mock_sock_instance.sendto.assert_called_once_with('encoded_data', ('localhost', 54321))

  def test_send_node_shutdown(self):
    self.send_node.shutdown()
    self.mock_sock_instance.close.assert_called_once()


class TestReceiveNode(unittest.TestCase):
  def setUp(self):
    self.mock_socket = patch('socket.socket').start()
    self.mock_sock_instance = self.mock_socket.return_value
    bind_addr = ('localhost', 12346)
    self.receive_node = ReceiveNode(bind_addr, DataCodec(datatype="command"))

  def tearDown(self):
    patch.stopall()

  def test_receive_node_initialization(self):
    self.mock_socket.assert_called_once_with(socket.AF_INET, socket.SOCK_DGRAM)
    self.mock_sock_instance.bind.assert_called_once_with(('localhost', 12346))
    self.mock_sock_instance.setblocking.assert_called_once_with(0)

  def test_receive_node_receive_with_data(self):
    mock_decode = MagicMock(return_value={"pc_state": "h"})
    self.receive_node.codec.decode = mock_decode
    self.mock_sock_instance.recvfrom.return_value = ('encoded_data', ('localhost', 54321))
    
    data, server = self.receive_node.receive()
    
    self.mock_sock_instance.recvfrom.assert_called_once_with(1024)
    mock_decode.assert_called_once_with('encoded_data')
    self.assertEqual(data, {"pc_state": "h"})
    self.assertEqual(server, ('localhost', 54321))

  def test_receive_node_receive_error(self):
    self.mock_sock_instance.recvfrom.side_effect = socket.error
    data, server = self.receive_node.receive()
    self.assertIsNone(data)
    self.assertIsNone(server)

  def test_receive_node_shutdown(self):
    self.receive_node.shutdown()
    self.mock_sock_instance.close.assert_called_once()


if __name__ == '__main__':
  unittest.main()
