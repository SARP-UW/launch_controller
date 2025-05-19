from sarp_codecs.codec import Codec
from collections import OrderedDict

# Map of all channel names to data types. For more info see:
# https://docs.python.org/3/library/struct.html#struct-format-strings
msg_schema = OrderedDict([
    ("timestamp", "Q"),
    ("example_channel_1", "i"),
    ("example_channel_2", "i"),
    ("example_channel_3", "i")
])

class TemplateCodec(Codec):
    def __init__(self):
        super(TemplateCodec, self).__init__(msg_schema)
