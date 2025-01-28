from codec import Codec
from collections import OrderedDict
from utils import load_config

# Map of all channel names to data types. For more info see:
# https://docs.python.org/3/library/struct.html#struct-format-strings
# f = float
# h = short
# ? = _Bool

class DataCodec(Codec):
	"""
	The template codec format for command and telemetry data.
	"""
	def __init__(self, datatype):
		# Intialize the gse master json class with loaded schema  
		gse_master = load_config()

		# Returns either 'prop' or 'fill'
		control_key = gse_master['control_key']

		# Extract the schema section for the given control_key
		data_config = gse_master[f'{datatype}_config']
		control_schema = data_config[control_key[0]]

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

		super(DataCodec, self).__init__(msg_schema)