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
    ("pc_state", "h"),
    ("pc_soft_armed", "?"),
    ("pc_fire", "?"),
    ("pc_redlines_armed", "?"),
    ("pc_pulse", "i"),
    ("pc_pdelay", "i")
])

class PropCommandCodec(Codec):
    def __init__(self):
        super(PropCommandCodec, self).__init__(msg_schema)