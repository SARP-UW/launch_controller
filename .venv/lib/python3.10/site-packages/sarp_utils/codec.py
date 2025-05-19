import struct

class Codec(object):
    """
    Base class for SARP message encoding/decoding
    """
    def __init__(self, msg_schema):
        self.msg_schema = msg_schema
        fmt_str = '!' + ''.join([self.msg_schema[k] for k in self.msg_schema])
        self.struct = struct.Struct(fmt_str)

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
