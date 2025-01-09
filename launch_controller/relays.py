import time
import json
import logging
#from pathlib import Path
from bitfield_utils import Utils
#import pdb
from util import config_util

logging.basicConfig(level=logging.DEBUG)

class Relays:
    """
    Relay state management class. Here we handle logic for requested commands. States are
    represented using an array of 10 integers. 0 means the relays IS NOT powered and 1 means it IS
    powered. Relays are read from left to right, so it would look something along the lines of:
     1   2   3   4   5   6   7   8   9   10
    [__, __, __, __, __, __, __, __, __, __]
    """
    # GPIO pins mapped to relay positions
    GPIO_MAPPING = [4, 17, 27, 22, 10, 9, 11, 5, 6, 13]

    """ 
    NOTE: IMPLEMENT DICTIONARY FOR MAP TO CLARIFY/SIMPLIFY PIN SELECTION
    """

    GPIO_MAP = {
        'prop': {
            'ignitor': GPIO_MAPPING[0],
            'injector': GPIO_MAPPING[1],
            'SV-02': GPIO_MAPPING[2],
            'fourth unknown': GPIO_MAPPING[3],
            'ox': GPIO_MAPPING[4],
            'fuel': GPIO_MAPPING[5],
            'seventh unknown': GPIO_MAPPING[6],
            'eighth unknown': GPIO_MAPPING[7],
            'ninth unknown': GPIO_MAPPING[8],
            'tenth unknown': GPIO_MAPPING[9]
        },
        'fill': {
            'BV-01': GPIO_MAPPING[0],
            'BV-02': GPIO_MAPPING[1],
            'BV-03': GPIO_MAPPING[2],
            'BV-04': GPIO_MAPPING[3],
            'BV-05': GPIO_MAPPING[4],
            'BV-06': GPIO_MAPPING[5],
            'BV-07': GPIO_MAPPING[6],
            'BV-08': GPIO_MAPPING[7],
            'BV-09': GPIO_MAPPING[8],
            'BV-10': GPIO_MAPPING[9]
        }
    }

    def __init__(self, GPIO, config_path="/home/pi/controller/GSE_master.json"):
        # Extract master json schema  
        self.config = config_util.load_config(config_path)

        # Retrieve control parameters directly from the master JSON
        control_key = self.config['control_key'] 
        # vent and closed state are both variable to the board it is on
        # vent state - all valves unpowered
        global VENT_STATE
        # closed state - all valves closed
        global CLOSED_STATE
        self._armed = True
        self._inj = False
        # Set up each pin as an output and set its initial state to LOW (OFF)
        for pin in self.GPIO_MAPPING:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)

        """ 
        NOTE: CODE COMMENTED OUT BELOW IS UNNECESSARY
        """
        #request = []
        # Define initial vent and closed states based on the control state (e.g., "fill")
        if control_key == "fill":
            VENT_STATE = [0, 0, 0, 0, 0, 1, 0, 1, 1, 0]
            CLOSED_STATE = [0, 0, 0, 0, 1, 0, 1, 0, 0, 0]
            #self._state = VENT_STATE
            #request = CLOSED_STATE
        else:
            VENT_STATE = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
            CLOSED_STATE = [0, 0, 1, 0, 1, 0, 0, 0, 0, 0]
            #self._state = VENT_STATE
            #request = CLOSED_STATE
        self._state = VENT_STATE
        # request = CLOSED_STATE

        # Set initial requested state to CLOSED_STATE and update relay statuses
        """ 
        NOTE: BE EXPLICIT IN SETTING TO 'CLOSED_STATE'
        """
        # self.request_state(request, 0)
        self.request_state(CLOSED_STATE, 0)
        self.update(GPIO)
        self._armed = False

        """
        NOTE TO SELF: CREATE DICTIONARY FOR 'SCR_tag' IN ORDER TO LOG WHAT IS HAPPENING
        """

        """
        NOTE TO SELF: CREATE DICTIONARY FOR 'SCR_tag' IN ORDER TO LOG WHAT IS HAPPENING
        """
        """
        SCR_tag tracks what triggered latest state change request. Meaning of each SCR_tag value:
        000 - Current state is that of the request from the user
        001 - Current state is a result of rejecting the request
        010 - Redline-commanded state
        011 - Auto-safing state
        100 - Pulse valve
        101 -
        110 -
        111 -
        """
        self._SCR_tag = 0

    def arm(self, GPIO):
        """
        Arm the relay system, allowing state changes
        """
        self._armed = True
        logging.info("ARMED")

    def disarm(self, GPIO):
        """
        Disarm the system and set it to CLOSED_STATE if not already there
        """
        if (self._state != CLOSED_STATE):
                self.request_state(CLOSED_STATE, 0)
                self.update(GPIO)
                logging.info("Setting closed state")
        self._armed = False
        logging.info("DISARMED")

    def is_armed(self):
        """ 
        Check if the relay system is armed
        """
        """ 
        Check if the relay system is armed
        """
        return self._armed
    
    def get_GPIO_map(self):
        """
        Simple method for getting correct GPIO map.
        """
        return self.GPIO_MAP[control_key]
    
    """
    NOTE: SETTER METHOD TO CLARIFY 'flip_state()' LOGIC
    """
    def set_state(self, index, value):
        """
        Set state of specified relay
        """
        self._requested_state[index] = value
    """
    NOTE: IMPLEMENT FUNCTIONALITY THAT RETURNS STATE OF SPECIFIED PIN IF INDEX IS PROVIDED
    """
    def get_state(self, index=-1):
        """
        Get the current state of relays or specified relay
        """
        if index == -1:
            return self._state
        
        return self._state[index]
    
    """
    NOTE: FLIPPER METHOD TO CLARIFY CODE IN METHODS SUCH AS 'PULSE_VALVE()'
    """
    def flip_state(self, index):
        """
        Flip specified relay state between 0 and 1
        """
        if self.get_state(index) == 0:
            self.set_state(index, 1)
        else:
            self.set_state(index, 0)
    """
    NOTE: METHOD FOR SIMPLIFYING CODE IN 'INITIATE_FIRE_SEQUENCE()'
    """
    def set_GPIO(self, GPIO, valve, state):
        if state == 'on':
            GPIO.output(self.GPIO_MAP[control_key][valve], GPIO.HIGH)
        elif state == 'off':
            GPIO.output(self.GPIO_MAP[control_key][valve], GPIO.LOW)
        else:
            # CREATE MORE ROBUST ERROR LOGGING
            logging.error("Failed to set valve state")

    def get_telemetry(self):
        """
        Generate a telemetry report with relay state and tags
        """
        """
        Generate a telemetry report with relay state and tags
        """
        states = Utils.num(self._state)

        telemetry_config = self.config['telemetry_config'][self._control[0]]

        """
        NOTE: CAN WE CHANGE THE NAMING CONVENTION IN THE JSON?
        """
        telemObject = {
            #need to go into specific control key first before going into the specific values from a specific subsection
            self.config['telemetry_config'][control_key[0]][control_key[0] + 'c_soft_armed']: self.is_armed(),
            self.config['telemetry_config'][control_key[0]][control_key[0] +'c_state']: states,
            self.config['telemetry_config'][control_key[0]][control_key[0] +'c_scr_tag']: self._SCR_tag
        }
        
        return telemObject

    def request_state(self, request, tag):
        """
        Store the requested state and set the corresponding _SCR_tag
        """
        """
        Store the requested state and set the corresponding _SCR_tag
        """
        self._requested_state = request.copy()
        self._SCR_tag = tag

    """
    NOTE: CLARIFY CODE IN THIS METHOD WITH 'set_GPIO()' METHOD
    """
    """
    NOTE: CLARIFY CODE IN THIS METHOD WITH 'set_GPIO()' METHOD
    """
    def INITIATE_FIRE_SEQUENCE(self, GPIO):
        """
        Handles the process of igniting and managing fuel/ox valves in a firing sequence
        """
        """
        Handles the process of igniting and managing fuel/ox valves in a firing sequence
        """
        if (self._inj):
            # Shut down injection if already active
            self.set_GPIO(GPIO, 'ox', 'off')
            self.set_GPIO(GPIO, 'ox', 'off')
            time.sleep(0.02)
            self.set_GPIO(GPIO, 'fuel', 'off')
            self.set_GPIO(GPIO, 'fuel', 'off')
            self._inj = False
            return

        if (self._armed):
            # Ignite the system by powering the ignitor and opening fuel/ox valves
            #self._inj = True 
            # power ignitor
            self.set_GPIO(GPIO, 'ignitor', 'on')
            print("Ignition on")
            # delay 2000 ms
            time.sleep(3.5) # Delay for ignition
            # open solenoid (injector)
            
            # Open solenoids for oxidizer and fuel
            self.set_GPIO(GPIO, 'ox', 'on')
            print("Oxidizer on")
            # Open solenoids for oxidizer and fuel
            self.set_GPIO(GPIO, 'ox', 'on')
            print("Oxidizer on")
            time.sleep(0.0055)
            self.set_GPIO(GPIO, 'fuel', 'on')
            print("Fuel on")
            # delay 30 ms
            #time.sleep(0.5)
            
            # close solenoid (injector)
            time.sleep(8.5)
            self.set_GPIO(GPIO, 'ox', 'off')
            self.set_GPIO(GPIO, 'fuel', 'off')
            self.set_GPIO(GPIO, 'ignitor', 'off')
            print("Oxidizer, fuel and ignition off")

    """
    NOTE: CORRECT BUGGED CODE, SIMPLIFY WITH 'flip_state()'
    """
            self.set_GPIO(GPIO, 'ox', 'off')
            self.set_GPIO(GPIO, 'fuel', 'off')
            self.set_GPIO(GPIO, 'ignitor', 'off')
            print("Oxidizer, fuel and ignition off")

    """
    NOTE: CORRECT BUGGED CODE, SIMPLIFY WITH 'flip_state()'
    """
    def PULSE_VALVE(self, GPIO, valve, delay):
        # flip requested valve
        # self._requested_state[valve] = not self._requested_state[valve]
        self.flip_state(valve)
        # self._requested_state[valve] = not self._requested_state[valve]
        self.flip_state(valve)
        self.update(GPIO)


        # valve delay
        time.sleep(delay/1000)

        # flip to previous state
        # self._requested_state[valve] = not self._requested_state[valve]
        self.flip_state(valve)
        # self._requested_state[valve] = not self._requested_state[valve]
        self.flip_state(valve)
        self.update(GPIO)

    def SET_VENT_STATE(self, GPIO, tag):
        """
        Set relays to safe state and update SCR tag with given tag.
        Set relays to safe state and update SCR tag with given tag.
        """
        self.request_state(VENT_STATE, tag)
        self.update(GPIO)
        time.sleep(0.5)
        # self._requested_state[1] = not self._requested_state[1]
        """
        NOTE: WHY ARE WE OPENING THIS VALVE?
        """
        self.flip_state(1)

        # self._requested_state[1] = not self._requested_state[1]
        """
        NOTE: WHY ARE WE OPENING THIS VALVE?
        """
        self.flip_state(1)

        self.update(GPIO)

    def SET_CLOSED_STATE(self, GPIO, tag):
        """
        Set relays to closed state and update SCR tag
        """
        self.request_state(CLOSED_STATE, tag)
        self.update(GPIO)

    def update(self, GPIO):
        """
        Update current relays states upon a change to _requested_state. We only update the state if
        the change is valid and when the relays are armed.
        """
        if (self._requested_state != self._state):
            if (self._armed):
                """
                NOTE: CLARIFY WITH EXPLICIT 'is_valid' BOOLEAN AND 'message' STRING
                """
                # update_validity = self.check_safe_update()
                # print("Validity: ", update_validity[0])
                is_valid, message = self.check_safe_update()
                print("Validity: ", is_valid)
                """
                NOTE: IMPLEMENT 'set_GPIO' LOGIC
                """
                if is_valid:
                    valves = list(self.get_GPIO_map())
                """
                NOTE: CLARIFY WITH EXPLICIT 'is_valid' BOOLEAN AND 'message' STRING
                """
                # update_validity = self.check_safe_update()
                # print("Validity: ", update_validity[0])
                is_valid, message = self.check_safe_update()
                print("Validity: ", is_valid)
                """
                NOTE: IMPLEMENT 'set_GPIO' LOGIC
                """
                if is_valid:
                    valves = list(self.get_GPIO_map())
                    for idx, relay_state in enumerate(self._requested_state):
                        if relay_state == 1:
                            self.set_GPIO(GPIO, valves[idx], 'on')
                        else:
                            self.set_GPIO(GPIO, valves[idx], 'off')
                            self.set_GPIO(GPIO, valves[idx], 'off')
                    self._state = self._requested_state.copy()
                    logging.info("SCR by '" + str(self._SCR_tag) + "' approved to " + str(self._state))
                else:
                    self._requested_state = self._state.copy()
                    logging.info("INVALID STATE REQUEST, ignoring request. " + message)
                    logging.info("INVALID STATE REQUEST, ignoring request. " + message)
            else:
                print(self._requested_state)
                self._requested_state = self._state.copy()
                self._SCR_tag = 1
                logging.info("DISARMED, ignoring SCR.")

    def check_safe_update(self):
        """
        Make sure we are not entering a prohibited state according to configuration files.
        """
        # initialize dicitionaries that will hold json file contents and read them in

        """
        NOTE - PLEASE CONFIRM: the master json looks like it only prohibits certain configurations in fill state.
                Therefore I added the condition that this check is only executed if the controller is in "fill" state
        """
        in_fill_state = control_key == "fill"
        if not in_fill_state:
            return (True, "")
        
        # relay_map = self.config["relay_maps"][self._control]
        relay_map = self.config["relay_maps"]["fill"]
        """
        NOTE: 'control_key' IS NOT A CHILD OF 'prohibited_states'
        """
        # prohibited_states = self.config["prohibited_states"][self._control]
        prohibited_states = self.config["prohibited_states"]

        # Confirm that all valve pairs in mutual exclusions are in the opposite state as one another
        # NOTE - maybe we can rename the master json to be less redundant here
        for mutex in prohibited_states["prohibited_states_mutual_exclusions"]:
            if (self._requested_state[relay_map[mutex[0]]] & self._requested_state[relay_map[mutex[1]]]):
                return (False, f"Mutual exclusion violation for {mutex[0]} and {mutex[1]}.")
        
        # Confirm that all valve pairs in mutual inclusions are in the same state as one another
        for mutex in prohibited_states["prohibited_states_mutual_inclusions"]:
                return (False, f"Mutual exclusion violation for {mutex[0]} and {mutex[1]}.")
        
        # Confirm that all valve pairs in mutual inclusions are in the same state as one another
        for mutex in prohibited_states["prohibited_states_mutual_inclusions"]:
            if (self._requested_state[relay_map[mutex[0]]]):
                if (self._requested_state[relay_map[mutex[0]]] != self._requested_state[relay_map[mutex[1]]]):
                  # mutual inclusion requirement not met
                    return (False, f"Mutual inclusion violation for {mutex[0]} and {mutex[1]}.")

        return (True, "")