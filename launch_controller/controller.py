import asyncio
import os
import time
import logging
from pathlib import Path


# Custom Modules
from relays import Relays
from sensors import Sensors
from data_codec import DataCodec
from network_node import SendNode, ReceiveNode
from utils import load_config, bitfield

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
fake_rpigpio.utils.install()
try:
    import RPi.GPIO as GPIO
except (RuntimeError, ModuleNotFoundError):
    print("Using mock GPIO for testing.")
    import GPIO as GPIO

class Controller:

    def __init__(self, config_path="GSE/launch_controller/gse_master.json"):
        # Set GPIO mode to BCM (Broadcom pin-numbering scheme)
        GPIO.setmode(GPIO.BCM)

        # Initalize the relays using the GPIO instance
        self.relays = Relays(GPIO)
        self.redlines_armed = False
        self.lastPing = time.time()
        self.og_time = 0.0
        self.first_time = True
        
        # Load GSE_master.json file
        gse_master = load_config()

        # gse_master will be either "fill" or "prop" to note what pi we are using
        # self._control = f['control_key'] 
        self. _control= gse_master['control_key']
        
        # Extract the pt_scale based on self._control from the loaded master file
        if self._control == "fill":
            pt_scaling = gse_master["pt_scales"]["fill_pt_scale"]
            self.sensors = Sensors(pt_scaling["max_p"], is_prop=False)
        else:
            pt_scaling = gse_master["pt_scales"]["prop_pt_scale"]
            self.sensors = Sensors(pt_scaling["max_p"], is_prop=True)

        addresses= {}   
        # Extract the "addresses" section from GSE_master.json
        addresses = gse_master["addresses"]

        # Initialize the telemtry server for sending data
        self.gc_address = addresses["GC_ADDR_IP"] 
        self.tlmServer = SendNode((addresses["TLM_SERVER_ADDR_IP"], addresses["TLM_SERVER_ADDR_PORT"]),
                                  (addresses["GC_ADDR_IP"], addresses["GC_ADDR_PORT"]),
                                  DataCodec("telemetry"))

        # initialize command receiver to receive commands from ground control
        self.cmdReceiver = ReceiveNode((addresses["CMD_RECEIVER_ADDR_IP"], addresses["CMD_RECEIVER_ADDR_PORT"]),
                                       DataCodec("command"))

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
        print(f"COMMAND {command}")
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
            stateRequest = bitfield(command[f"{self._control[0]}c_state"])
            if len(stateRequest) > 10:
                # do special command stuff
                # ???????????
                pass
            # Request state change from relays
            self.relays.request_state(stateRequest, 0)

    def actuator_checks(self):
        self.checkRedlines()  # Ensure safety thresholds are checked
        self.processRequest()  # Process any new commands
        self.relays.update(GPIO)  # Update relays based on current state
        
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

    def pingAddress(self):
        return os.system("ping -c 1 -w 10 " + str(self.gc_address))
        
    def actualCheckNetwork(self, count):
         # Ping the ground control address
            response = self.pingAddress()

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
            return count
                     
    def actualSendTelemetry(self):
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
        
           
    async def updateActuators(self):
        """
        Periodically updates relays while checking for safety and processing commands.
        """
        while True:
            self.actuator_checks()
            await asyncio.sleep(.5)  # Pause for 500ms before the next update cycle



    async def sendTelemetry(self):
        """
        Construct the codec for telemetry.
        """
        while True:
            self.actualSendTelemetry()
            await asyncio.sleep(.5)  # Pause for 500ms before the next telemetry cycle

        
    async def checkNetwork(self):
        """
        Periodically checks network connection by pinging the ground control server.
        """
        count = 0
        while True:
            count = self.actualCheckNetwork(count)
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