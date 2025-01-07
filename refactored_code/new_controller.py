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
from network_node import SendNode, ReceiveNode, Network
from bitfield_utils import Utils
from util import config_util
import RPi.GPIO as GPIO

class Controller:

    def __init__(self):
        self.__initializeGPIO()
        self.__initializeRelays()
        self.__extractKeyValues()
        self.__initialize_telemetry()
        
    def __initializeRelays(self):
        GPIO.setmode(GPIO.BCM)
        self.relays = Relays(GPIO)
        self.redlines_armed = False
        self.lastPing = time.time()
        self.og_time = 0.0
        self.first_time = True

    def __initializeGPIO(self):
        try:
            import RPi.GPIO as GPIO
        except (RuntimeError, ModuleNotFoundError):
            print("Spoofing GPIO.")
            import fake_rpigpio.utils
            fake_rpigpio.utils.install()
            import RPi.GPIO as GPIO
    
    def __extractKeyValues(self):
        self.config = config_util.load_config("../launch_controller/controller/GSE_master.json")
        control_key = self.config['control_key']
        
        if control_key == "fill":
            pt_scaling = self.config["pt_scales"]["fill_pt_scale"]
            self.sensors = FillSensors(pt_scaling["max_p"])
        else:
            pt_scaling = self.config["pt_scales"]["prop_pt_scale"]
            self.sensors = PropSensors(pt_scaling["max_p"])
        
        self.addresses = self.config["addresses"]

    def __initialize_telemetry(self):
        self.ground_countrol_address = self.addresses["addresses"]["GC_ADDR_IP"]
        self.telem_server = Network(((self.addresses["addresses"]["TLM_SERVER_ADDR_IP"], self.addresses["addresses"]["TLM_SERVER_ADDR_PORT"]),
                                  (self.addresses["addresses"]["GC_ADDR_IP"], self.addresses["addresses"]["GC_ADDR_PORT"])))
                  
        self.command_receiver = Network(self.addresses["addresses"]["CMD_RECEIVER_ADDR_IP"], self.addresses["addresses"]["CMD_RECEIVER_ADDR_PORT"])

    def __initialize_logger(self):
        self.soft_arm = False
        self.telem_logger = self.__set_logger('telem', 'placeholder file name')
        self.control_logger = self.__set_logger('control', 'placeholder file name')

    def __set_logger(self, name, filename):
        handler = logging.FileHandler(filename)
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        return logger
        
    