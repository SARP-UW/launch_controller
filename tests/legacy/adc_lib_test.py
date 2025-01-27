import time
from ADS1219_lib import ADS1219

ADC_GAIN = 4
ADC_ADDRS = [0x40, 0x41, 0x42, 0x43]

adcs = [ADS1219(1, i) for i in range(4)]

for adc in adcs:
	adc.set_gain(ADC_GAIN)

adcs[0].setExternalReference(5)

while True:
	for adc in adcs:
		print(adc.convertToV(adc.readDifferential_0_1()))
		print(adc.convertToV(adc.readDifferential_2_3()))
	time.sleep(1)
