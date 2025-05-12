import json
import asyncio
import os
import time
import pdb
import logging
logging.basicConfig(level=logging.INFO)
from relays import Relays
from prop_sensors import PropSensors
from fill_sensors import FillSensors
from fill_telem_codec import FillTelemCodec
from prop_telem_codec import PropTelemCodec
from fill_command_codec import FillCommandCodec
from prop_command_codec import PropCommandCodec
from network_node import SendNode, ReceiveNode
from bitfield_utils import Utils

try:
    import RPi.GPIO as GPIO
except (RuntimeError, ModuleNotFoundError):
    print("Spoofing GPIO.")
    import fake_rpigpio.utils
    fake_rpigpio.utils.install()
    import RPi.GPIO as GPIO

class Controller:

    def __init__(self):
        GPIO.setmode(GPIO.BCM)
        # control.txt will be either "fill" or "prop" to note what pi we are using
        self._control = open("/home/pi/controller/control.txt", "r").read()[0:4]
        self.relays = Relays(GPIO)
        self.redlines_armed = False
        self.lastPing = time.time()
        self.og_time = 0.0
        self.first_time = True
        # pull appropriate sensor file
        with open("/home/pi/controller/" + self._control +"_pt_scale.json") as pt_scalings:
            pt_scaling = json.load(pt_scalings)
            if self._control == "fill":
                self.sensors = FillSensors(pt_scaling["pt_scale"]["max_p"])
            else:
                self.sensors = PropSensors(pt_scaling["pt_scale"]["max_p"])

        addresses= {}
        with open("/home/pi/controller/addresses.json") as addresses_f:
            addresses = json.load(addresses_f)

        self.gc_address = addresses["addresses"]["GC_ADDR_IP"]
        self.tlmServer = SendNode((addresses["addresses"]["TLM_SERVER_ADDR_IP"], addresses["addresses"]["TLM_SERVER_ADDR_PORT"]),
                                  (addresses["addresses"]["GC_ADDR_IP"], addresses["addresses"]["GC_ADDR_PORT"]),
                                  eval(f"{self._control.capitalize()}TelemCodec()"))

        self.cmdReceiver = ReceiveNode((addresses["addresses"]["CMD_RECEIVER_ADDR_IP"], addresses["addresses"]["CMD_RECEIVER_ADDR_PORT"]),
                                       eval(f"{self._control.capitalize()}CommandCodec()"))

        # set config for log files
        self.soft_arm = False
        self.telem_logger = self.set_logger('telem', 'telem.log')
        self.cntrl_logger = self.set_logger('cntrl', 'control.log')

        # self.relays.arm(GPIO)

        # self.relays.PULSE_VALVE(GPIO, 1, 2000)

    def set_logger(self, name, filename):
        handler = logging.FileHandler(filename)
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        return logger

    def processRequest(self):
        """
        Process the command to update relays. Here we will make sure the requested update is a
        valid one.
        """
        command, addr = self.cmdReceiver.receive()
        print("-------------------------------")
        print(command)
        print(addr)
        print("-------------------------------")
        if command is not None:
            self.cntrl_logger.info(command)

            # check if we are firing
            if self._control == "prop":
                if command[f"{self._control[0]}c_fire"]:
                    self.relays.INITIATE_FIRE_SEQUENCE(GPIO)

            # pulse valve
            pulse_valve = command[f"{self._control[0]}c_pulse"]
            if pulse_valve >= 0:
                pulse_delay = command[f"{self._control[0]}c_pdelay"]
                print(f"Pulsing valve {pulse_valve}")
                self.relays.PULSE_VALVE(GPIO, pulse_valve, pulse_delay)

            # check if software is armed
            if command[f"{self._control[0]}c_soft_armed"]:
                self.soft_arm = True
                self.relays.arm(GPIO)
            else:
                self.soft_arm = False
                self.relays.disarm(GPIO)

            if command[f"{self._control[0]}c_redlines_armed"]:
                self.redlines_armed = True
            else:
                self.ignore_redlines = True

            stateRequest = Utils.bitfield(command[f"{self._control[0]}c_state"])
            if len(stateRequest) > 10:
                # do special command stuff
                pass
            self.relays.request_state(stateRequest, 0)

    def checkRedlines(self):
        """
        Check PT readings for thresholds to update valves in event of dangerous state realized from
        sensor readings.
        """
        if (self.redlines_armed):
            pass
        else:
            pass

    async def updateActuators(self):
        """
        Update relays but first check if the update is safe.
        """
        while True:
            # Override SCR if applicable
            self.checkRedlines()
            # Submit SCR if command
            self.processRequest()
            # Apply latest SCR
            self.relays.update(GPIO)
            # logging.info("update actuators")
            await asyncio.sleep(.5)

    async def sendTelemetry(self):
        """
        Construct the codec for telemetry.
        """
        while True:
            # Retrieve telemetry from sensors and relays
            sensorTelem = self.sensors.get_telemetry()
            relayTelem = self.relays.get_telemetry()
            print("\nSENSOR TELEM")
            print(sensorTelem)
            print("\nRELAY TELEM")
            print(relayTelem)
            fullTelem = {}
            # Add time stamp to fullTelem
            if self.first_time:
                self.og_time = time.time()
                self.first_time = False
            fullTelem[f"{self._control[0]}c_timestamp"] = time.time() - self.og_time

            # Add redlines_armed to fullTelem
            fullTelem[f"{self._control[0]}c_redlines_armed"] = self.redlines_armed

            # Add sensors and relays to telemetry
            fullTelem.update(sensorTelem)
            fullTelem.update(relayTelem)
            print("\nFULL TELEM")
            print(fullTelem)
            try:
                self.tlmServer.send(fullTelem)
                print("success")
            except Exception as e:
                self.telem_logger.error('Network error:')
            if self.soft_arm:
                self.telem_logger.info(fullTelem)
            await asyncio.sleep(.5)

    async def checkNetwork(self):
        """
            ping gc to check connection
            set network status based on response
        """
        count = 0
        while True:
            # ping gc
            response = os.system("ping -c 1 -w 10 " + str(self.gc_address))

            # if valid ping
            if response == 0:
                # keep track of last successful ping
                count = 0
                self.lastPing = time.time()
            else:
                # check 10 minute time out
                count += 1
                if count > 1:
                    self.cntrl_logger.error("Bad network state detected")
                    if time.time() - self.lastPing > 600:
                        # disarm and vent
                        self.relays.SET_VENT_STATE(GPIO, 3)
                        # self.relays.disarm(GPIO) # disarm sets closed, we want to leave open
                    # set to closed state if not venting
                    else:
                        self.relays.SET_CLOSED_STATE(GPIO, 3)

            await asyncio.sleep(10)


    def main(self):
        pool = asyncio.get_event_loop()
        pool.create_task(self.checkNetwork())
        pool.create_task(self.updateActuators())
        pool.create_task(self.sendTelemetry())
        pool.run_forever()


if __name__ == "__main__":
    c = Controller()
    c.main()
