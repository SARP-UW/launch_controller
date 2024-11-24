"""
The template codec format for telemetry.
"""
import json
from sarp_utils.codec import Codec 
from collections import OrderedDict
from utils import Utils

# Map of all channel names to data types. For more info see:
# https://docs.python.org/3/library/struct.html#struct-format-strings
# f = float
# h = short
# ? = _Bool

class TelemCodec(Codec):
    def __init__(self): 
         # Intialize the gse master json class with loaded schema           
        # json_path = '/home/pi/controller/GSE_master.json'
        gse_master = Utils.load_config("/home/pi/controller/GSE_master.json")
        control_key = gse_master['control_key']
        assert control_key == 'prop'
        
        # with open(json_path, 'r') as file:
        #     schema_json = json.load(file)

        # Extract the schema section for the given control_key
        telemetry_config = gse_master.get('telemetry_config', {})
        assert telemetry_config == {
        "p": {
          "pc_timestamp": "f",
          "pc_cpu_temp": "f",
          "pc_hard_armed": "?",
          "pc_soft_armed": "?",
          "pc_redlines_armed": "?",
          "pc_state": "h",
          "pc_scr_tag": "h",
          "adc_channels": {
            "pc_adc1_c1": "f",
            "pc_adc1_c2": "f",
            "pc_adc1_c3": "f",
            "pc_adc1_c4": "f",
            "pc_adc2_c1": "f",
            "pc_adc2_c2": "f",
            "pc_adc2_c3": "f",
            "pc_adc2_c4": "f"
          }
        },
        "f": {
          "fc_timestamp": "f",
          "fc_cpu_temp": "f",
          "fc_hard_armed": "?",
          "fc_soft_armed": "?",
          "fc_redlines_armed": "?",
          "fc_state": "h",
          "fc_scr_tag": "h",
          "adc_channels": {
            "fc_adc1_c1": "f",
            "fc_adc1_c2": "f",
            "fc_adc1_c3": "f",
            "fc_adc1_c4": "f",
            "fc_adc2_c1": "f",
            "fc_adc2_c2": "f",
            "fc_adc2_c3": "f",
            "fc_adc2_c4": "f"
          }
        }
    }    
        control_schema = telemetry_config.get(control_key[0], {})
        assert control_schema == {
          "pc_timestamp": "f",
          "pc_cpu_temp": "f",
          "pc_hard_armed": "?",
          "pc_soft_armed": "?",
          "pc_redlines_armed": "?",
          "pc_state": "h",
          "pc_scr_tag": "h",
          "adc_channels": {
            "pc_adc1_c1": "f",
            "pc_adc1_c2": "f",
            "pc_adc1_c3": "f",
            "pc_adc1_c4": "f",
            "pc_adc2_c1": "f",
            "pc_adc2_c2": "f",
            "pc_adc2_c3": "f",
            "pc_adc2_c4": "f"
          }
        }

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
        