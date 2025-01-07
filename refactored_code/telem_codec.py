"""
The template codec format for telemetry.
"""
import json
from codec import Codec 
from collections import OrderedDict
from util import config_util

# Map of all channel names to data types. For more info see:
# https://docs.python.org/3/library/struct.html#struct-format-strings
# f = float
# h = short
# ? = _Bool

class TelemCodec(Codec):
    def __init__(self): 
        # Intialize the gse master json class with loaded schema          
        self.config = config_util.load_config("/home/pi/controller/GSE_master.json")
        control_key = self.config['control_key'] 

        # Extract the schema section for the given control_key
        control_schema = self.config["telemetry_config"][control_key[0]]

        # Create an OrderedDict to maintain the order
        msg_schema = OrderedDict()

        # Add top-level values
        for key, value in control_schema.items():
            if key != 'adc_channels':  # Exclude the 'adc_channels' key
                msg_schema[key] = value
        
        # Add adc_channels values if present
        adc_channels = control_schema.get('adc_channels', {})
        for key, value in adc_channels.items():
            msg_schema[key] = value

        super(TelemCodec, self).__init__(msg_schema)
        
        