import struct
from collections import OrderedDict

class Codec(object):
    """
    Base class for SARP message encoding/decoding
    """
    def __init__(self, msg_schema):
        self.formatted_schema = self.prepare_schema(msg_schema)
        fmt_str = '!' + ''.join([self.formatted_schema[k] for k in self.formatted_schema])
        self.struct = struct.Struct(fmt_str)


    def prepare_schema(self, input_schema):
        formatted_schema = OrderedDict()
        for key, value in input_schema:
            formatted_schema[key] = value



    def encode(self, msg):
        """
        Args:
            msg: a dictionary of channels:values matching the msg_schema
        Returns: a bytestring formatted packet
        """
        msg_vals = [msg[channel] for channel in self.msg_schema]
        return self.struct.pack(*msg_vals)

    def decode(self, packet):
        """
        Args:
            packet: a bytestring formatted packet
        Returns: a dictionary of channels:values matching the msg_schema
        """
        msg_vals = self.struct.unpack(packet)
        msg = {}
        for name, value in zip(self.msg_schema, msg_vals):
            msg[name] = value
        return msg
