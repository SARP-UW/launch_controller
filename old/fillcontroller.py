import json
import asyncio
import time
import pdb
import logging
logging.basicConfig(level=logging.DEBUG)
from relays import Relays
from sensors import Sensors
from fill_telem_codec import FillTelemCodec
from command_codec import CommandCodec
from network_node import SendNode, ReceiveNode
from bitfield_utils import Utils

try:
    import RPi.GPIO as GPIO
except (RuntimeError, ModuleNotFoundError):
    print("Spoofing GPIO.")
    import fake_rpigpio.utils
    fake_rpigpio.utils.install()
    import RPi.GPIO as GPIO

class FillController:

    def __init__(self):
        GPIO.setmode(GPIO.BCM)
        self.relays = Relays(GPIO)
        self.sensors = Sensors()
        self.ignore_redlines = False
        self.networkOkay = False

        addresses= {}
        with open("addresses.json") as addresses_f:
            addresses = json.load(addresses_f)

        self.tlmServer = SendNode((addresses["addresses"]["TLM_SERVER_ADDR_IP"], addresses["addresses"]["TLM_SERVER_ADDR_PORT"]),
                                  (addresses["addresses"]["GC_ADDR_IP"], addresses["addresses"]["GC_ADDR_PORT"]),
                                  FillTelemCodec())
        self.cmdReceiver = ReceiveNode((addresses["addresses"]["CMD_RECEIVER_ADDR_IP"], addresses["addresses"]["CMD_RECEIVER_ADDR_PORT"]),
                                       CommandCodec())

    def processRequest(self):
        """
        Process the command to update relays. Here we will make sure the requested update is a
        valid one.
        """
        command, addr = self.cmdReceiver.receive()
        if command is not None:
            logging.info(command)
            if (command["fc_soft_armed"] == True):
                self.relays.arm()
            else:
                self.relays.disarm()
            stateRequest = Utils.bitfield(command["fc_state"])
            if len(stateRequest) > 10:
                # do special command stuff
                pass
            self.relays.request_state(stateRequest, 0)

    def checkRedlines(self):
        """
        Check PT readings for thresholds to update valves in event of dangerous state realized from
        sensor readings.
        """
        if not self.ignore_redlines:
            pass
        else:
            pass

    async def updateActuators(self):
        while True:
            # Override SCR if applicable
            self.checkRedlines()
            # Submit SCR if command
            self.processRequest()
            # Apply latest SCR
            self.relays.update(GPIO)
            logging.info("update actuators")
            await asyncio.sleep(.5)

    async def sendTelemetry(self):
        while True:
            # Retrieve telemetry from sensors and relays
            sensorTelem = self.sensors.get_telemetry()
            relayTelem = self.relays.get_telemetry()

            fullTelem = {}

            # Add time stamp to fullTelem
            fullTelem["fc_timestamp"] = time.time()

            # Add sensors and relays to telemetry
            fullTelem.update(sensorTelem)
            fullTelem.update(relayTelem)

            # pdb.set_trace()
            self.tlmServer.send(fullTelem)

            logging.info(fullTelem)
            await asyncio.sleep(1)

    def main(self):
        pool = asyncio.get_event_loop()
        pool.create_task(self.updateActuators())
        pool.create_task(self.sendTelemetry())
        pool.run_forever()


if __name__ == "__main__":
    fc = FillController()
    fc.main()
