import logging
logging.basicConfig(level=logging.DEBUG)

try:
    from gpiozero import CPUTemperature
    import ADC_Driver
    ONTARGET = True
except:
    ONTARGET = False

ADC_GAIN = 4
ADC_SAMPLE_RATE = 20

# max pressure in 1000 PSI
# PT_MAX_P = [1, 1, 1, 1, 5, 5, 0, 0]


class FillSensors:
    def __init__(self, pt_scale):
        self.adc = []
        self.PT_scaling = pt_scale
        if (ONTARGET):
            self.cpu = CPUTemperature()
            for i in range(1, 9):
                self.adc.append(ADC_Driver.ADS1219(i, ADC_GAIN, ADC_SAMPLE_RATE))
        else:
            self.adc = [0, 0, 0, 0, 0, 0, 0, 0]

    def get_cpu_temp(self):
        if (ONTARGET):
            return self.cpu.temperature
        else:
            return 0

    def get_adc_readings(self):
        readings = []
        if (ONTARGET):
            for id, channel in enumerate(self.adc):
                # readings.append(channel.read_voltage())
                readings.append(channel.read_pressure(max_p=(self.PT_scaling[id])))
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
