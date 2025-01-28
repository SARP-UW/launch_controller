"""
The template codec format for telemetry.
"""
from codec import Codec 
from collections import OrderedDict
from utils import load_config

# Map of all channel names to data types. For more info see:
# https://docs.python.org/3/library/struct.html#struct-format-strings
# f = float
# h = short
# ? = _Bool

class TelemCodec(Codec):
    def __init__(self): 
         # Intialize the gse master json class with loaded schema           
        gse_master = load_config()
            
        control_key = gse_master['control_key']
        # assert control_key == 'prop'
        
        # with open(json_path, 'r') as file:
        #     schema_json = json.load(file)

        # Extract the schema section for the given control_key
        telemetry_config = gse_master['telemetry_config']
        # assert "p" in telemetry_config and "f" in telemetry_config

        control_schema = telemetry_config[control_key[0]]
        # expected_keys = [
        #     "pc_timestamp", "pc_cpu_temp", "pc_hard_armed", "pc_soft_armed",
        #     "pc_redlines_armed", "pc_state", "pc_scr_tag", "adc_channels"
        # ]
        # assert all(key in control_schema for key in expected_keys)


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
        
        