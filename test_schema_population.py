import json
from collections import OrderedDict


# Path to control.txt
key = open('/Users/cooperreynolds/Desktop/sarp/controller_new/control.txt', "r").read()[0]
   
# Path to telemetry_config.json
json_path = '/Users/cooperreynolds/Desktop/sarp/controller_new/command_config.json'
control_key = key[0]


try:
    # Load the JSON file
    with open(json_path, 'r') as file:
        schema_json = json.load(file)
    
    # Debug print to check loaded JSON
    print("Loaded JSON schema:")
    print(json.dumps(schema_json, indent=4))
    
    # Extract the schema section for the given control_key
    # 'telemetry' for telem file and 'command' for command
    schema = schema_json.get('command', {})
    print(f"Schema extracted: {schema}")
    control_schema = schema.get(control_key, {})
    print(f"Control schema for '{control_key}': {control_schema}")
    
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

    # Check if the OrderedDict is empty
    if not msg_schema:
        raise ValueError("The OrderedDict 'msg_schema' is empty after parsing the JSON file.")
    
    # Print the OrderedDict to verify
    print("Populated msg_schema:")
    for k, v in msg_schema.items():
        print(f"({k}, {v})")

except FileNotFoundError:
    print(f"Error: The file at {json_path} was not found.")
except json.JSONDecodeError:
    print("Error: Failed to decode JSON from the file.")
except ValueError as e:
    print(e)
except Exception as e:
    print(f"An unexpected error occurred: {e}")

