"""
Codec format for commands.
"""

from sarp_utils.codec import Codec
from collections import OrderedDict

# Map of all channel names to data types. For more info see:
# https://docs.python.org/3/library/struct.html#struct-format-strings
# h = short
# ? = _Bool
msg_schema = OrderedDict([
    ("fc_state", "h"),
    ("fc_soft_armed", "?"),
    ("fc_redlines_armed", "?"),
    ("fc_pulse", "i"),
    ("fc_pdelay", "i")
])

class FillCommandCodec(Codec):
    def __init__(self):
        super(FillCommandCodec, self).__init__(msg_schema)
