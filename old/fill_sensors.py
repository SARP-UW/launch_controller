import logging
logging.basicConfig(level=logging.DEBUG)

try:
    from gpiozero import CPUTemperature
    import PROP_ADC_Driver
    ONTARGET = True
except:
    ONTARGET = False

ADC_GAIN = 2/3
ADC_SAMPLE_RATE = 20

# max pressure in 1000 PSI
# PT_MAX_P = [1, 1, 1, 1, 5, 5, 0, 0]


class FillSensors:
    def __init__(self, pt_scale):
        self.adc = []
        self.PT_scaling = pt_scale
        if (ONTARGET):
            self.cpu = CPUTemperature()
            self.adc.append(PROP_ADC_Driver.ADS1115(gain=ADC_GAIN, addr=0x48))
            self.adc.append(PROP_ADC_Driver.ADS1115(gain=ADC_GAIN, addr=0x49))

    def get_cpu_temp(self):
        if (ONTARGET):
            return self.cpu.temperature
        else:
            return 0

    def get_adc_readings(self):
        readings = []
        if (ONTARGET):
            for num, adc in enumerate(self.adc):
                for channel in range(0, 4):
                    # 4 pts with max 1k psi
                    # readings.append(self.PT_scaling[num*4 + channel])
                    readings.append(adc.read_pressure(channel, max_p=self.PT_scaling[num*4 + channel]))
                    # readings.append(adc.read_voltage(channel))
        else:
            return [0, 0, 0, 0, 0, 0, 0, 0]
        return readings

    def get_hard_armed(self):
        return False

# !!! should not default to false when we're actually using it
    def get_telemetry(self, read_channels=True):
        """
        Send the cpu temp and each of the adc readings over telemetry. If read_channels
        is false, then we return 0 instead of the true readings.
        """
        readings = self.get_adc_readings()
        if not read_channels:
            readings = [0, 0, 0, 0, 0, 0, 0, 0]

        telemObject = {
            "fc_cpu_temp": self.get_cpu_temp(),
            "fc_adc1_c1" : readings[0],
            "fc_adc1_c2" : readings[1],
            "fc_adc1_c3" : readings[2],
            "fc_adc1_c4" : readings[3],
            "fc_adc2_c1" : readings[4],
            "fc_adc2_c2" : readings[5],
            "fc_adc2_c3" : readings[6],
            "fc_adc2_c4" : readings[7],
            "fc_hard_armed" : self.get_hard_armed()
        }

        return telemObject
