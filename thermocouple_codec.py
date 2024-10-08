from sarp_utils.codec import Codec
from collections import OrderedDict

# Map of all channel names to data types. For more info see:
# https://docs.python.org/3/library/struct.html#struct-format-strings
msg_schema = OrderedDict([
    ("tc_timestamp", "f"),
    ("tc1", "f"),
    ("tc2", "f"),
    ("tc3", "f"),
    ("tc4", "f"),
    ("tc5", "f"),
    ("tc6", "f"),
    ("tc7", "f")
])

class ThermocoupleCodec(Codec):
    def __init__(self):
        super(ThermocoupleCodec, self).__init__(msg_schema)
