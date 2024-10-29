"""
The template codec format for telemetry.
"""
import json
from sarp_utils.codec import Codec 
from collections import OrderedDict

# Map of all channel names to data types. For more info see:
# https://docs.python.org/3/library/struct.html#struct-format-strings
# f = float
# h = short
# ? = _Bool

class TelemCodec(Codec):
    def __init__(self):        
        json_path = '/home/pi/controller/GSE_master.json'
        control_key = json_path['control_key']
        
        with open(json_path, 'r') as file:
            schema_json = json.load(file)

        # Extract the schema section for the given control_key
        telemetry_config = schema_json.get('telemetry_config', {})
        control_schema = telemetry_config.get(control_key, {})

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
        