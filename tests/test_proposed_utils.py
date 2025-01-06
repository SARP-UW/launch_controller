import sys, os
# Looks rough, but adds launch_controller to PATH from within any directory
sys.path.append(os.getcwd()[0:os.getcwd().find('/GSE') + 4] + '/launch_controller')
import proposed_utils as utils

class TestUtils:
# TESTING GET_ROOT_PATH()
	def test_root_path_contains_root_directory(self):
		root_path = utils.get_root_path()
		print(root_path)
		assert '/GSE' in root_path


# TESTING GET_CONFIG_PATH()
	def test_config_path_contains_config_file(self):
		config_path = utils.get_config_path()
		print(config_path)
		assert '/GSE/launch_controller/gse_master.json' in config_path


# TESTING LOAD_CONFIG()
	def test_config_is_dictionary(self):
		config = utils.load_config()
		print(config)
		assert isinstance(config, dict)


# TESTING BITFIELD()
	def test_bitfield_is_list(self):
		print('Input -> Output')
		for i in range(10):
			bitfield = utils.bitfield(i)
			print(f'{i} -> {bitfield}')
			assert isinstance(bitfield, list)

	# Create more tests


# TESTING NUM()
	def test_num_is_int(self):
		print('Input -> Output')
		for i in range(10):
			bitfield = utils.bitfield(i)
			num = utils.num(bitfield)
			print(f'{bitfield} -> {num}')
			assert isinstance(num, int)

	# Create more tests