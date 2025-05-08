import logging
logging.basicConfig(level=logging.DEBUG)

from ads1115 import ADS1115
try:
    #from gpiozero import CPUTemperature
    from ads1115 import ADS1115
    ONTARGET = True
except:
    print("PROP ADC not imported")
    ONTARGET = False

ADC_GAIN = 4
ADC_SAMPLE_RATE = 20

class PropSensors:
    def __init__(self, pt_scale):
        self.adc = []
        self.PT_scaling = pt_scale
        if (ONTARGET):
            self.cpu = {"temperature": 0} #CPUTemperature()
            self.adc.append(ADS1115(gain=ADC_GAIN, addr=0x48))
            self.adc.append(ADS1115(gain=ADC_GAIN, addr=0x49))

    def get_cpu_temp(self):
        if (ONTARGET):
            return self.cpu["temperature"]
        else:
            return 0

    def get_adc_readings(self):
        readings = []
        if (ONTARGET):
            for num, adc in enumerate(self.adc):
                for channel in range(0, 4):
                    # 4 pts with max 1k psi
                    readings.append(adc.read_pressure(channel, max_p=self.PT_scaling[num * 4 + channel]))
        else:
            readings = [0, 0, 0, 0, 0, 0, 0, 0]
            #for adc in self.adc:
            #      for channel in range(0, 4):
            #        readings.append(0)
        return readings

    def get_hard_armed(self):
        return False

    def get_telemetry(self):
        """
        Send the cpu temp and each of the adc readings over telemetry.
        """
        readings = self.get_adc_readings()
        telemObject = {
            "pc_cpu_temp": self.get_cpu_temp(),
            "pc_adc1_c1" : readings[0],
            "pc_adc1_c2" : readings[1],
            "pc_adc1_c3" : readings[2],
            "pc_adc1_c4" : readings[3],
            "pc_adc2_c1" : readings[4],
            "pc_adc2_c2" : readings[5],
            "pc_adc2_c3" : readings[6],
            "pc_adc2_c4" : readings[7],
            "pc_hard_armed" : True #self.get_hard_armed()
        }
        print(telemObject)

        return telemObject
