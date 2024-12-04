import json
import asyncio
import os
import time
import pdb
import logging

# Custom Modules
from relays import Relays
from prop_sensors import PropSensors
from fill_sensors import FillSensors
from telem_codec import TelemCodec
from command_codec import CommandCodec
from network_node import SendNode, ReceiveNode
from bitfield_utils import Utils #TODO: Change the name of either one of the utils functions.
from utils import Utils 

# Configure logging to output information to console
logging.basicConfig(level=logging.INFO)

# # Block to import RPi.GPIO for controlling GPIO pins on Raspberry PI
# try:
#     import RPi.GPIO as GPIO
# except (RuntimeError, ModuleNotFoundError):
#     # If theres an issue imports spoof GPIO library
#     print("Spoofing GPIO.")
#     import fake_rpigpio.utils
#     fake_rpigpio.utils.install()
#     import RPi.GPIO as GPIO

import fake_rpigpio.utils
fake_rpgpio.utils.install()
import Rpi.GPIO as GPIO 

class Controller:

    def __init__(self):
        # Set GPIO mode to BCM (Broadcom pin-numbering scheme)
        GPIO.setmode(GPIO.BCM)

        # Initalize the relays using the GPIO instance
        self.relays = Relays(GPIO)
        self.redlines_armed = False
        self.lastPing = time.time()
        self.og_time = 0.0
        self.first_time = True
        
        #  # Load GSE_master.json file
        # with open("/home/pi/controller/GSE_master.json") as gse_master_f:
        #     gse_master = json.load(gse_master_f)

        gse_master = Utils.load_config("/home/pi/controller/GSE_master.json")

        # gse_master will be either "fill" or "prop" to note what pi we are using
        # self._control = gse_master_f['control_key'] 
        self. _control= gse_master['control_key']
        assert self._control == "prop" or "fill" #TEST
        
        # Extract the pt_scale based on self._control from the loaded master file
        if self._control == "fill":
            pt_scaling = gse_master["pt_scales"]["fill_pt_scale"]
            assert "max_p" is in pt_scaling and "min_v" is in pt_scaling and "max_v" is in pt_scaling
            #assert pt_scaling == {"max_p" : [1000, 1000, 1000, 1000, 1000, 1000, 1000, 5000],"max_v" : 4.5,"min_v" : 0.5}
            self.sensors = FillSensors(pt_scaling["max_p"])
        else:
            pt_scaling = gse_master["pt_scales"]["prop_pt_scale"]
            assert "max_p" is in pt_scaling and "max_v" is in pt_scaling and "min_v" is in pt_scaling
            # assert pt_scaling == {"max_p" : [0, 0, 0, 0, 0, 0, 0, 0],"max_v" : 5,"min_v" : 0.5}
            self.sensors = PropSensors(pt_scaling["max_p"])

        addresses= {}   
        # Extract the "addresses" section from GSE_master.json
        addresses = gse_master["addresses"]
        #TEST
        assert "TLM_SERVER_ADDR_IP" is in addresses and "TLM_SERVER_ADDR_PORT" is in addresses and "CMD_RECEIVER_ADDR_IP" is in addresses
        assert addresses == {     
        "TLM_SERVER_ADDR_IP": "",
        "TLM_SERVER_ADDR_PORT": 31000,
        "CMD_RECEIVER_ADDR_IP": "",
        "CMD_RECEIVER_ADDR_PORT": 31002,
        "GC_ADDR_IP": "10.0.0.100",
        "GC_ADDR_PORT": 31000
        }

        # Initialize the telemtry server for sending data
        self.gc_address = addresses["addresses"]["GC_ADDR_IP"] 
        self.tlmServer = SendNode((addresses["addresses"]["TLM_SERVER_ADDR_IP"], addresses["addresses"]["TLM_SERVER_ADDR_PORT"]),
                                  (addresses["addresses"]["GC_ADDR_IP"], addresses["addresses"]["GC_ADDR_PORT"]),
                                  TelemCodec())

        # initialize command receiver to receive commands from ground control
        self.cmdReceiver = ReceiveNode((addresses["addresses"]["CMD_RECEIVER_ADDR_IP"], addresses["addresses"]["CMD_RECEIVER_ADDR_PORT"]),
                                       CommandCodec())

        # set up loggers for telemtry and control logs
        self.soft_arm = False
        self.telem_logger = self.set_logger('telem', 'telem.log')
        self.cntrl_logger = self.set_logger('cntrl', 'control.log')

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
        if command is not None:
            self.cntrl_logger.info(command)

            # Check if the system is controlling propellant ("prop" mode) and initiate fire sequence
            if self._control[0] == 'p':
                if command['pc_fire']:
                    self.relays.INITIATE_FIRE_SEQUENCE(GPIO)

            # Pulse a valve if a pulse command was received
            pulse_valve = command[f"{self._control[0]}c_pulse"]
            if pulse_valve >= 0:
                self.relays.PULSE_VALVE(GPIO, pulse_valve, command[f"{self._control[0]}c_pdelay"])

            # Arm or disarm the software-controlled relays based on the command
            if command[f"{self._control[0]}c_soft_armed"]:
                self.soft_arm = True
                self.relays.arm(GPIO)
            else:
                self.soft_arm = False
                self.relays.disarm(GPIO)

            # Arm redlines if requested
            if command[f"{self._control[0]}c_redlines_armed"]:
                self.redlines_armed = True
            else:
                self.ignore_redlines = True

            # Process the relay state from the command
            stateRequest = Utils.bitfield(command[f"{self._control[0]}c_state"])
            if len(stateRequest) > 10:
                # do special command stuff
                # ???????????
                pass
            # Request state change from relays
            self.relays.request_state(stateRequest, 0)

    def checkRedlines(self):
        """
        Check PT readings for thresholds to update valves in event of dangerous state realized from
        sensor readings.
        """
        # ????????
        if (self.redlines_armed):
            pass
        else:
            pass

    async def updateActuators(self):
        """
        Periodically updates relays while checking for safety and processing commands.
        """
        while True:
            self.checkRedlines()  # Ensure safety thresholds are checked
            self.processRequest()  # Process any new commands
            self.relays.update(GPIO)  # Update relays based on current state
            await asyncio.sleep(.5)  # Pause for 500ms before the next update cycle


    async def sendTelemetry(self):
        """
        Construct the codec for telemetry.
        """
        while True:
            # Retrieve telemetry from sensors and relays
            sensorTelem = self.sensors.get_telemetry()
            relayTelem = self.relays.get_telemetry()

            fullTelem = {}
            # Add a timestamp to the telemetry data
            if self.first_time:
                self.og_time = time.time()
                self.first_time = False
            fullTelem[f"{self._control[0]}c_timestamp"] = time.time() - self.og_time

            # Add the redlines_armed status to the telemetry
            fullTelem[f"{self._control[0]}c_redlines_armed"] = self.redlines_armed

            # Merge sensor and relay telemetry into the full telemetry package
            fullTelem.update(sensorTelem)
            fullTelem.update(relayTelem)
            
            # Try sending the telemetry, log errors if they occur
            try:
                self.tlmServer.send(fullTelem)
            except Exception as e:
                self.telem_logger.error('Network error:')
            if self.soft_arm:
                # Log telemetry if system is armed
                self.telem_logger.info(fullTelem)
            await asyncio.sleep(.5)  # Pause for 500ms before the next telemetry cycle

    async def checkNetwork(self):
        """
        Periodically checks network connection by pinging the ground control server.
        """
        count = 0
        while True:
            # Ping the ground control address
            response = os.system("ping -c 1 -w 10 " + str(self.gc_address))

            # if valid ping
            if response == 0:
                # If the ping is successful, reset the count and update the lastPing timestamp
                count = 0
                self.lastPing = time.time()
            else:
                # If the ping fails, increment the count and check for a timeout
                count += 1
                if count > 1:
                    self.cntrl_logger.error("Bad network state detected")
                    # If no valid ping for over 10 minutes, vent the system
                    if time.time() - self.lastPing > 600:
                        self.relays.SET_VENT_STATE(GPIO, 3)
                        # self.relays.disarm(GPIO) # disarm sets closed, we want to leave open
                    # Otherwise, set the system to a closed state
                    else:
                        self.relays.SET_CLOSED_STATE(GPIO, 3)

            await asyncio.sleep(10)  # Pause for 10 seconds before the next network check


    def main(self):
        # Create an event loop and run the async tasks
        pool = asyncio.get_event_loop()
        pool.create_task(self.checkNetwork())  # Check network connection periodically
        pool.create_task(self.updateActuators())  # Periodically update actuators
        pool.create_task(self.sendTelemetry())  # Periodically send telemetry
        pool.run_forever()  # Keep the loop running indefinitely


if __name__ == "__main__":
    c = Controller()
    c.main()