import Adafruit_ADS1x15
import busio
import board
from adafruit_ads1x15.analog_in import AnalogIn
import adafruit_ads1x15.ads1115 as ADS

class ADS1115:
    # Pressure transducer specs
    # ADC bit
    # bits = 15 even though ADC is marketed for 16 bits
    # missing bit is used to signify the sign
    bits = 15

    # Choose a gain of 1 for reading voltages from 0 to 4.09V.
    # Or pick a different gain to change the range of voltages that are read:
    #  - 2/3 = +/-6.144V
    #  -   1 = +/-4.096V
    #  -   2 = +/-2.048V
    #  -   4 = +/-1.024V
    #  -   8 = +/-0.512V
    #  -  16 = +/-0.256V
    gain_ranges = {2 / 3: 6.144, 1: 4.096, 2: 2.048, 4: 1.024, 8: 0.512, 16: 0.256}
    min_v = 0.5
    max_v = 4.5

    def __init__(self, gain, addr):
        #self.adc = Adafruit_ADS1x15.ADS1115(address=addr, i2c=busio.I2C(board.SCL, board.SDA))
        # self.adc = i2c.readfrom_into(addr, result)
        i2c = busio.I2C(board.SCL, board.SDA)
        result = bytearray(1)
        self.adc = ADS.ADS1115(i2c, address=addr)
        print("info from addresss")
        print(int.from_bytes(result, "big"))
        self.gain = gain

    # Returns voltage
    def read_voltage(self, channel):
        print("reading from adc")
        chan = AnalogIn(self.adc, channel)
        print(chan.value, chan.voltage)
        bit_value = chan.value
        #bit_value = self.adc.read_adc(channel, gain=self.gain)
        
        # OLD VOLTAGE CODE
        #voltage = ADS1115.gain_ranges[self.gain] / (2 ** ADS1115.bits - 1) * bit_value

        # NEW VOLTAGE CODE
        voltage = chan.voltage
        return voltage

    # Returns pressure
    # If channel_pos or channel_neg is None, uses non-differential voltage
    # If channel_pos and channel_neg are not None, uses differential voltage
    def read_pressure(self, channel, max_p):
        voltage = self.read_voltage(channel)
        pressure = (voltage - ADS1115.min_v) * (max_p / (ADS1115.max_v - ADS1115.min_v))
        return pressure
