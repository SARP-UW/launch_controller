import json
import logging
logging.basicConfig(level=logging.DEBUG)

try:
    from gpiozero import CPUTemperature
    import PROP_ADC_Driver
except:
    pass

# telemetry_handlers = {
#     "addresses" : handle_addresses,
#     "command_config" : handle_command_config,
#     "prop_fill_prohibited_states" : handle_prop_fill_prohibited_states,
#     "pt_scales" : handle_pt_scales,
#     "relay_maps" : handle_relay_maps,
#     "prohibited_states" : handle_prohibited_states,
#     "sensor_map" : handle_sensor_map,
#     "telemetry_config" : handle_telemetry_config
# }


# add these to gse_master.json?
ADC_GAIN_PROP = 4
ADC_SAMPLE_RATE_PROP = 20 #same for both fill + prop, need separate?
ADC_GAIN_FILL = 2/3

class Sensors:
    def __init__(self, pt_scale, is_prop=None, test_adc_drivers=None, test_cpu_temp=None):
        self.is_fill = not is_prop
        self.is_prop = is_prop
        self.adc = []
        self.PT_scaling = pt_scale
        self.ontarget = True

        try:
            self.cpu = CPUTemperature()
        except:
            self.ontarget = False

        if (self.ontarget):
            if self.is_fill:
                self.adc.append(PROP_ADC_Driver.ADS1115(gain=ADC_GAIN_FILL, addr=0x48))
                self.adc.append(PROP_ADC_Driver.ADS1115(gain=ADC_GAIN_FILL, addr=0x49))
            else:
                self.adc.append(PROP_ADC_Driver.ADS1115(gain=ADC_GAIN_PROP, addr=0x48))
                self.adc.append(PROP_ADC_Driver.ADS1115(gain=ADC_GAIN_PROP, addr=0x49))  

        if test_adc_drivers and test_cpu_temp:
            self.adc = test_adc_drivers
            self.cpu = test_cpu_temp

    def get_cpu_temp(self):
        """
        Return temperature if connected to Pi Zero ?
        """
        if (self.ontarget):
            return self.cpu.temperature
        else:
            return 0

    def get_adc_readings(self):
        readings = []
        if (self.ontarget):
            for num, adc in enumerate(self.adc):
                for channel in range(0, 4):
                    # 4 pts with max 1k psi
                    # readings.append(self.PT_scaling[num*4 + channel])
                    readings.append(adc.read_pressure(channel, max_p=self.PT_scaling[num * 4 + channel]))
        else:
            if self.is_prop:
                for adc in self.adc:
                    # figure out why this code in prop sensors was written this way, what is adc for?
                    for channel in range(0, 4):
                        readings.append(0)
            else:
                return [0, 0, 0, 0, 0, 0, 0, 0]
        return readings

    def get_hard_armed(self):
        return False

    # read_channels defaulted to True in fill_sensors.py, but not in prop_sensors
    # again, figure out why
    def get_telemetry(self, read_channels=True):
        """
        Send the cpu temp and each of the adc readings over telemetry.
        """
        readings = self.get_adc_readings()
        # this was only included in fill_sensors
        if not read_channels and self.is_fill:
            readings = [0, 0, 0, 0, 0, 0, 0, 0]
        
        # need a function to parse gse_json for object instead of hard coding
        if self.is_prop:
            # convert from telemetry_config
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
                "pc_hard_armed" : self.get_hard_armed()
            }
        else:
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
