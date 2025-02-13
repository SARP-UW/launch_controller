import os
import json
import logging
from bitarray import bitarray

"""
The name of the root folder where the application is expected to operate. This is set to '/GSE'.
"""
ROOT_FOLDER = '/GSE'

def get_root_path():
	"""
	Retrieves the absolute path to the root folder (/GSE) based on the current working directory.
	"""
    # Get path to any current working directory
    path = os.getcwd()
    
	# Find the index of the name of the root folder in the path string
    index_of_root_folder_in_path = path.find(ROOT_FOLDER)
    
	# The root path is everything up until that index plus the name of the root folder
    root_path = path[0:index_of_root_folder_in_path] + ROOT_FOLDER
    
    return root_path


def get_config_path():
	"""
	Retrieves the absolute path to the root folder (/GSE) based on the current working directory.
	"""
    return get_root_path() + '/launch_controller/gse_master.json'


def load_config(config_path=get_config_path()):
    """
    Loads the configuration from a JSON file. If no path is provided, it defaults to the path returned by get_config_path().
    """
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Error loading config file: {e}")
        return None
    

def bitfield(n):
	"""
	Convert input integer into bit array. All integers sent are with leading to allow for zero
	padding.
	"""
	b = [1 if digit=='1' else 0 for digit in bin(n)[2:]]
	# remove leading one used to preserve leading 0's
	del b[0]
	# pad right side of list with zeroes
	if len(b) < 10:
		b += [0] * (10 - len(b))
	return b


def num(b):
	"""
	Converts an integer into a bit array. The function ensures that the resulting bit array is 10 bits long by padding with zeros if necessary.
	"""
	assert(len(b) == 10), "Invalid state array length."
	c = b.copy()
	# insert a leading one to preserve leading zeros (THIS MUST BE REMOVED BY bitfield())
	c.insert(0, 1)
	return int(bitarray(c).to01(), 2)