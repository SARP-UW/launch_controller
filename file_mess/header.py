import struct
from hamming import Hamming

class TelemetryHeader:
    def __init__(self, transmission_length=32, delimiter="1111"):
        self.transmission_length = transmission_length
        self.delimiter = delimiter

    def create_header(self):
        # Create header as a byte stream: first 4 bytes for transmission length, followed by delimiter
        header = struct.pack('!I', self.transmission_length)
        header += self.delimiter.encode()
        return header

    def parse_header(self, header_bytes):
        # Extract header information from bytes
        transmission_length = struct.unpack('!I', header_bytes[:4])[0]
        delimiter = header_bytes[4:].decode()
        return transmission_length, delimiter

class TelemetryHeader:
    def __init__(self, transmission_length=32, delimiter="1111"):
        """
        Initializes the header with transmission length and delimiter.

        :param transmission_length: The number of bits expected in each data segment.
        :param delimiter: The bit pattern used to separate data values in the bit stream.
        """
        self.transmission_length = transmission_length
        self.delimiter = delimiter

    def create_header(self):
        """
        Create a header that contains the transmission length and delimiter.

        :return: A dictionary representing the header information.
        """
        return {
            "transmission_length": self.transmission_length,
            "delimiter": self.delimiter
        }
