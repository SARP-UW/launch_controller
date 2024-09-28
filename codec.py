import hamming
from telemetry_header import TelemetryHeader
import struct

class Codec:
    def __init__(self, msg_schema, header):
        self.msg_schema = msg_schema
        self.header = header
        self.header_data = self.header.create_header()

        # Define the struct format string based on msg_schema
        fmt_str = '!' + ''.join([self.msg_schema[k] for k in self.msg_schema])
        self.struct = struct.Struct(fmt_str)

        # Initialize Hamming encoder and decoder for [8,4]
        self.hamming_encoder = hamming.Hamming8_4()
        self.hamming_decoder = hamming.Hamming8_4()

    def encode(self, msg):
        """
        Encode the message and prepend header information.

        :param msg: A dictionary of channels:values matching the msg_schema
        :return: A bytestring formatted packet with header
        """
        # Encode message
        msg_vals = [msg[channel] for channel in self.msg_schema]
        encoded_msg = self.struct.pack(*msg_vals)
        
        # Encode header
        header_bytes = f"{self.header_data['transmission_length']}{self.header_data['delimiter']}".encode()
        encoded_header = self.hamming_encoder.encode(header_bytes)
        
        # Combine header and message
        return encoded_header + encoded_msg

    def decode(self, packet):
        """
        Decode the packet by separating header and message, and then decoding each.

        :param packet: A bytestring formatted packet with header
        :return: A dictionary of channels:values matching the msg_schema
        """
        # Assuming header is the first 16 bytes (for Hamming [8,4] encoded header)
        header_length = 16
        header_data = packet[:header_length]
        encoded_msg = packet[header_length:]

        # Decode header
        decoded_header = self.hamming_decoder.decode(header_data)
        header_str = decoded_header.decode()
        self.header_data = self.header.parse_header({
            "transmission_length": int(header_str[:2]),
            "delimiter": header_str[2:]
        })

        # Decode message
        msg_vals = self.struct.unpack(encoded_msg)
        msg = {}
        for name, value in zip(self.msg_schema, msg_vals):
            msg[name] = value
        return msg

    def check_schema_mismatch(self, decoded_msg):
        """
        Checks for schema mismatches and logs any discrepancies to a text file.

        :param decoded_msg: The decoded message dictionary
        """
        mismatches = []
        for encoded_name in self.msg_schema:
            if encoded_name not in decoded_msg:
                continue
            encoded_value = decoded_msg[encoded_name]

            if encoded_name != decoded_msg[encoded_name]:
                mismatches.append((encoded_name, encoded_value))

        if mismatches:
            with open('schema_mismatches.txt', 'a') as f:
                for name, value in mismatches:
                    f.write(f"Mismatch detected - Name: {name}, Value: {value}\n")
