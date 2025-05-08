import struct
import time
import busio
import board

_CHANNEL_MASK = 0xE0
_GAIN_MASK = 0x10
_DR_MASK = 0xC
_CM_MASK = 0x2
_VREF_MASK = 0x1

_COMMAND_RESET = 0x6
_COMMAND_START_SYNC = 0x8
_COMMAND_POWERDOWN = 0x2
_COMMAND_RDATA = 0x10
_COMMAND_RREG_CONFIG = 0x20
_COMMAND_RREG_STATUS = 0x24
_COMMAND_WREG_CONFIG = 0x40

_DRDY_MASK = 0x80  
_DRDY_NO_NEW_RESULT = 0x0     # No new conversion result available
_DRDY_NEW_RESULT_READY = 0x80 # New conversion result ready


class ADS1219: 

    CHANNEL_AIN0_AIN1 = 0x0   # Differential P = AIN0, N = AIN1 (default)
    CHANNEL_AIN2_AIN3 = 0x20  # Differential P = AIN2, N = AIN3
    CHANNEL_AIN1_AIN2 = 0x40  # Differential P = AIN1, N = AIN
    CHANNEL_AIN0  = 0x60       # Single-ended AIN0
    CHANNEL_AIN1 = 0x80       # Single-ended AIN1
    CHANNEL_AIN2 = 0xA0       # Single-ended AIN2
    CHANNEL_AIN3 = 0xC0       # Single-ended AIN3
    CHANNEL_MID_AVDD = 0xE0   # Mid-supply   P = AVDD/2, N = AVDD/2
    
    GAIN_1X = 0x0             # Gain = 1 (default)
    GAIN_4X = 0x10            # Gain = 4
        
    DR_20_SPS   = 0x0         # Data rate = 20 SPS (default)
    DR_90_SPS   = 0x4         # Data rate = 90 SPS
    DR_330_SPS  = 0x8         # Data rate = 330 SPS
    DR_1000_SPS = 0xC         # Data rate = 1000 SPS
    
    CM_SINGLE = 0x0           # Single-shot conversion mode (default)
    CM_CONTINUOUS = 0x2       # Continuous conversion mode

    VREF_INTERNAL = 0x0       # Internal 2.048V reference (default)
    VREF_EXTERNAL = 0x1       # External reference
    
    VREF_INTERNAL_MV = 2048   # Internal reference voltage = 2048 mV
    VREF_EXTERNAL_MV = 5000
    POSITIVE_CODE_RANGE = 0x7FFFFF # 23 bits of positive range 

    '''
    ADS1219 is the device driver for the embedded ADC's on SARP's Fill Controller.
    There are four ADC's with two differential channels each for a total of 8 
    channels.

    Note:
        Channel 8 has a fixed ADC driver that amplifies weak signals 4x. If
        used with 4x gain, total gain is 16x.

    Args:
        input (int): ADC Channels 1-8
        gain (int) : Gain can be 1 or 4
        data_rate  : How many samples per second are performed.

    ''' 
    def __init__(self, input=1, gain=1, data_rate=20):
        self._ID = input
        self._i2c = busio.I2C(board.SCL, board.SDA)
        self._address = 0x40
        self._gain = 1
        if self.set_channel(input) is False:
            print('Channel {} must be 1-8'.format(input))
        if self.set_gain(gain) is False:
            print('A gain of {} must be 1 or 4'.format(gain))
        if self.set_data_rate(data_rate) is False:
            print('Data rate {} must be 20, 90, 330, or 1000'.format(data_rate))
        self.set_vref(ADS1219.VREF_INTERNAL)
        self.set_conversion_mode(ADS1219.CM_SINGLE)
        self.reset()

    ''' @ Broadcasts I2C scan for all ADS1219's alive.
      ' @ Note: Useful for debugging
      ' @ Return: None 
    ''' 
    def scan(self):
        adc_found = self._i2c.scan()
        print('ADCs found: {}'.format(', '.join(hex(adc) for adc in adc_found)))

    ''' @ Read data directly from ADS1219
      ' @ Return: Unconverted Data
    ''' 
    def read_raw_data(self):
        if ((self.read_config() & _CM_MASK) == 0x0):
            self.start_sync()
            # loop until conversion is completed
            while((self.read_status() & _DRDY_MASK) == _DRDY_NO_NEW_RESULT):
                time.sleep(.1)        
            
        rreg = struct.pack('B', _COMMAND_RDATA) 
        self._i2c.writeto(self._address, rreg)
        data = bytearray(3)
        self._i2c.readfrom_into(self._address, data)
        return struct.unpack('>I', b'\x00' + data)[0]

    ''' @ Converts raw data from ADC to actual voltage. It divides out 
      '   the gain.
      ' @ Return: Voltage in milli-volts
    ''' 
    def read_voltage(self):
        result = 16777057 - self.read_raw_data()
        return ( result * ADS1219.VREF_INTERNAL_MV  / 
                 ADS1219.POSITIVE_CODE_RANGE) #/ self._gain

    ''' @ Converts voltage into pressure. max_pressure depends on PT.
      ' @ Return: Pressure in PSI
    ''' 
    def read_pressure(self, min_v=0.5, max_v=4.5, max_p=0.0):
        # read voltage gets millivolts, convert to volts
        voltage = self.read_voltage() / 1000
        pressure = (voltage - min_v) * (max_p / (max_v - min_v))
        return pressure

    def get_ID(self):
        return self._ID

    def _read_modify_write_config(self, mask, value):
        as_is = self.read_config()
        to_be = (as_is & ~mask) | value 
        wreg = struct.pack('BB', _COMMAND_WREG_CONFIG, to_be)
        self._i2c.writeto(self._address, wreg)
        
    def read_config(self):
        rreg = struct.pack('B', _COMMAND_RREG_CONFIG) 
        self._i2c.writeto(self._address, rreg)
        config = bytearray(1)
        self._i2c.readfrom_into(self._address, config)
        return config[0]
    
    def read_status(self):
        rreg = struct.pack('B', _COMMAND_RREG_STATUS) 
        self._i2c.writeto(self._address, rreg)
        status = bytearray(1)
        self._i2c.readfrom_into(self._address, status)
        return status[0]

    def set_channel(self, input):
        if (input==1):
            self._address = 0x40
            self._read_modify_write_config(_CHANNEL_MASK, ADS1219.CHANNEL_AIN0_AIN1)
            return True
        elif(input==2):
            self._address = 0x40
            self._read_modify_write_config(_CHANNEL_MASK, ADS1219.CHANNEL_AIN2_AIN3)
            return True
        elif(input==3):
            self._address = 0x41
            self._read_modify_write_config(_CHANNEL_MASK, ADS1219.CHANNEL_AIN0_AIN1)
            return True
        elif(input==4):
            self._address = 0x41
            self._read_modify_write_config(_CHANNEL_MASK, ADS1219.CHANNEL_AIN2_AIN3)
            return True
        elif(input==5):
            self._address = 0x42
            self._read_modify_write_config(_CHANNEL_MASK, ADS1219.CHANNEL_AIN0_AIN1)
            return True
        elif(input==6):
            self._address = 0x42
            self._read_modify_write_config(_CHANNEL_MASK, ADS1219.CHANNEL_AIN2_AIN3)
            return True
        elif(input==7):
            self._address = 0x43
            self._read_modify_write_config(_CHANNEL_MASK, ADS1219.CHANNEL_AIN0_AIN1)  
            return True        
        elif(input==8):
            self._address = 0x43
            self._read_modify_write_config(_CHANNEL_MASK, ADS1219.CHANNEL_AIN2_AIN3)
            return True
        else :
            return False
        
    def set_gain(self, gain):
        if gain is 1:
            self._gain = 1
            self._read_modify_write_config(_GAIN_MASK, ADS1219.GAIN_1X)
        elif gain is 4:
            self._gain = 4
            self._read_modify_write_config(_GAIN_MASK, ADS1219.GAIN_4X)
        else:
            return False
        
    def set_data_rate(self, data_rate):
        if data_rate is 20:
            self._read_modify_write_config(_DR_MASK, ADS1219.DR_20_SPS)
            return True
        elif data_rate is 90:
            self._read_modify_write_config(_DR_MASK, ADS1219.DR_90_SPS)
            return True
        elif data_rate is 330:
            self._read_modify_write_config(_DR_MASK, ADS1219.DR_330_SPS)
            return True
        elif data_rate is 1000:
            self._read_modify_write_config(_DR_MASK, ADS1219.DR_1000_SPS)
            return True
        else :
            return False

    def set_conversion_mode(self, cm):
        self._read_modify_write_config(_CM_MASK, cm)
        
    def set_vref(self, vref):
        self._read_modify_write_config(_VREF_MASK, vref)

    def read_data_irq(self):
        rreg = struct.pack('B', _COMMAND_RDATA) 
        self._i2c.writeto(self._address, rreg)
        data = bytearray(3)
        self._i2c.readfrom_into(self._address, data)
        return struct.unpack('>I', b'\x00' + data)[0]
        
    def reset(self):
        data = struct.pack('B', _COMMAND_RESET)
        self._i2c.writeto(self._address, data)  

    def start_sync(self):
        data = struct.pack('B', _COMMAND_START_SYNC)
        self._i2c.writeto(self._address, data)        

    def powerdown(self):
        data = struct.pack('B', _COMMAND_POWERDOWN)
        self._i2c.writeto(self._address, data)