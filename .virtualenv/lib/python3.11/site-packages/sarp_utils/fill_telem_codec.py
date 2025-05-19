"""
The template codec format for fill telemetry.
"""
from sarp_utils.codec import Codec
from collections import OrderedDict

# Map of all channel names to data types. For more info see:
# https://docs.python.org/3/library/struct.html#struct-format-strings
# f = float
# h = short
# ? = _Bool
msg_schema = OrderedDict([
    ("fc_timestamp", "f"),
    ("fc_cpu_temp", "f"),
    ("fc_adc1_c1", "f"),
    ("fc_adc1_c2", "f"),
    ("fc_adc1_c3", "f"),
    ("fc_adc1_c4", "f"),
    ("fc_adc2_c1", "f"),
    ("fc_adc2_c2", "f"),
    ("fc_adc2_c3", "f"),
    ("fc_adc2_c4", "f"),
    ("fc_hard_armed", "?"),
    ("fc_soft_armed", "?"),
    ("fc_redlines_armed", "?"),
    ("fc_state", "h"),
    ("fc_scr_tag", "h")
])

class FillTelemCodec(Codec):
    def __init__(self):
        super(FillTelemCodec, self).__init__(msg_schema)
