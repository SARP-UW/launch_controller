"""
The template codec format for command.
"""
import json
from sarp_utils.codec import Codec
from collections import OrderedDict
from util import config_util

# Map of all channel names to data types. For more info see:
# https://docs.python.org/3/library/struct.html#struct-format-strings
# f = float
# h = short
# ? = _Bool

class CommandCodec(Codec):
    def __init__(self):
        # Intialize base Codec class from gse_master with loaded schema            
        self.config = config_util.load_config("/home/pi/controller/GSE_master.json")
        control_key = self.config['control_key'] 

        # Extract the schema section for the given control_key
        control_schema = self.config['command_config'][control_key[0]]

        # Create an OrderedDict to maintain the order
        msg_schema = OrderedDict()

        # Add top-level values
        for key, value in control_schema.items():
            msg_schema[key] = value

        super(CommandCodec, self).__init__(msg_schema)
        