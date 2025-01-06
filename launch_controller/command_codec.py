"""
The template codec format for command.
"""
import json
from codec import Codec
from collections import OrderedDict
from utils import Utils

# Map of all channel names to data types. For more info see:
# https://docs.python.org/3/library/struct.html#struct-format-strings
# f = float
# h = short
# ? = _Bool

class CommandCodec(Codec):
    def __init__(self):
        # Intialize base Codec class from gse_master with loaded schema 
        #            
        # gse_master = Utils.load_config("/home/pi/controller/GSE_master.json")

        with open('/Users/arjun/Documents/GSE/launch_controller/gse_master.json', 'r') as f:
            gse_master = json.load(f)
            
        control_key = gse_master['control_key'] 
        assert control_key == 'prop'

        # Extract the schema section for the given control_key
        command_config = gse_master.get('command_config', {})
        #TEST
        assert "p" in command_config and "f" in command_config

        
        control_schema = command_config.get(control_key[0], {})
        #TEST
        expected_keys = ["pc_state", "pc_soft_armed", "pc_fire", "pc_redlines_armed", "pc_pulse", "pc_pdelay"]
        assert all(key in control_schema for key in expected_keys)


        # Create an OrderedDict to maintain the order
        msg_schema = OrderedDict()

        # Add top-level values
        for key, value in control_schema.items():
            msg_schema[key] = value

        super(CommandCodec, self).__init__(msg_schema)
        