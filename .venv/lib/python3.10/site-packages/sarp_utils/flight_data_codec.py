"""
The template codec format for flight data.
"""
from sarp_utils.codec import Codec
from collections import OrderedDict

# Map of all channel names to data types. For more info see:
# https://docs.python.org/3/library/struct.html#struct-format-strings
# f = float
# h = short
# ? = _Bool
msg_schema = OrderedDict([
    ("fd_timestamp", "f"),
    ("fd_accel_x", "f"),
    ("fd_accel_y", "f"),
    ("fd_accel_z", "f"),
    ("fd_lat", "f"),
    ("fd_longit", "f"),
    ("fd_fuel_p", "f"),
    ("fd_he_p", "f"),
    ("fd_comb_p", "f"),
    ("fd_av_p", "f"),
    ("fd_ox_p", "f"),
    ("fd_temp", "f"),
    ("fd_humid", "f"),
    ("fd_press", "f"),
    ("fd_alt", "f")
])

class FlightDataCodec(Codec):
    def __init__(self):
        super(FlightDataCodec, self).__init__(msg_schema)
