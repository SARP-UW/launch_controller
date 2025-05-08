"""
The template codec format for command.
"""
import json
from sarp_utils.codec import Codec
from collections import OrderedDict

# Map of all channel names to data types. For more info see:
# https://docs.python.org/3/library/struct.html#struct-format-strings
# f = float
# h = short
# ? = _Bool

class CommandCodec(Codec):
    def __init__(self):
        # Intialize base Codec class with loaded schema    
        self._control = open("/home/pi/controller/control.txt", "r").read()[0]
        
        json_path = '/home/pi/controller/command_config.json'
        control_key = self._control[0]
        
        with open(json_path, 'r') as file:
            schema_json = json.load(file)

        # Extract the schema section for the given control_key
        schema = schema_json.get('command', {})
        control_schema = schema.get(control_key, {})

        # Create an OrderedDict to maintain the order
        msg_schema = OrderedDict()

        # Add top-level values
        for key, value in control_schema.items():
            msg_schema[key] = value
        

        super(CommandCodec, self).__init__(msg_schema)
        