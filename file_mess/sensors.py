import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.DEBUG)

try:
    from gpiozero import CPUTemperature
    import ADC_Driver
    ONTARGET = True
except:
    ONTARGET = False

ADC_GAIN = 4
ADC_SAMPLE_RATE = 20

class Sensors:
    def __init__(self, config_path="/home/pi/controller/telemetry_config.json"):
        self.adc = []
        self.config = self.load_config(config_path)
        self._control = open("/home/pi/controller/control.txt", "r").read()[0]
        if (ONTARGET):
            self.cpu = CPUTemperature()
            for i in range(1, 9):
                self.adc.append(ADC_Driver.ADS1219(i, ADC_GAIN, ADC_SAMPLE_RATE))

    def load_config(self, config_path):
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Error loading config file: {e}")
            return None
        
    def get_cpu_temp(self):
        if (ONTARGET):
            return self.cpu.temperature
        else:
            return 0

    def get_adc_readings(self):
        readings = []
        if (ONTARGET):
            for channel in self.adc:
                readings.append(channel.read_voltage())
        else:
            for channel in self.adc:
                readings.append(0)
        return readings

    def get_hard_armed(self):
        return False

    def get_telemetry(self):
        """
        Send the cpu temp and each of the adc readings over telemetry.
        """
        readings = self.get_adc_readings()
        telemObject = {
            self.config['telemetry'][self._control[0]][self._control[0] + 'c_cpu_temp']: self.get_cpu_temp()
        }

        adc_channels = self.config['telemetry'][self._control[0]]['adc_channels']
        for i, channel_name in enumerate(adc_channels):
            if i < len(readings):
                telemObject[channel_name] = readings[i]
        
        telemObject[self.config['telemetry'][self._control[0]][self._control[0] + 'c_hard_armed']] = self.get_hard_armed()
          
        return telemObject
