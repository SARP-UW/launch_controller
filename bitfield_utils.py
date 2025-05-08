from bitarray import bitarray

class Utils:
	"""
	Class that holds functions for bit and integer manipulation.
	"""
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
		Convert bitfield array to integer.
		"""
		assert(len(b) == 10), "Invalid state array length."
		c = b.copy()
		# insert a leading one to preserve leading zeros (THIS MUST BE REMOVED BY bitfield())
		c.insert(0, 1)
		return int(bitarray(c).to01(), 2)
