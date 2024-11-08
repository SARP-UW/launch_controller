"""
The template codec format for propulsion telemetry.
"""
from sarp_utils.codec import Codec
from collections import OrderedDict

# Map of all channel names to data types. For more info see:
# https://docs.python.org/3/library/struct.html#struct-format-strings
# f = float
# h = short
# ? = _Bool
msg_schema = OrderedDict([
    ("pc_timestamp", "f"),
    ("pc_cpu_temp", "f"),
    ("pc_adc1_c1", "f"),
    ("pc_adc1_c2", "f"),
    ("pc_adc1_c3", "f"),
    ("pc_adc1_c4", "f"),
    ("pc_adc2_c1", "f"),
    ("pc_adc2_c2", "f"),
    ("pc_adc2_c3", "f"),
    ("pc_adc2_c4", "f"),
    ("pc_hard_armed", "?"),
    ("pc_soft_armed", "?"),
    ("pc_redlines_armed", "?"),
    ("pc_state", "h"),
    ("pc_scr_tag", "h")
])

class PropTelemCodec(Codec):
    def __init__(self):
        super(PropTelemCodec, self).__init__(msg_schema)
