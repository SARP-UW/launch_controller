import time
import json
import logging
logging.basicConfig(level=logging.DEBUG)
from sarp_utils.bitfield_utils import Utils


class Relays:
    """
    Relay state management class. Here we handle logic for requested commands. States are
    represented using an array of 10 integers. 0 means the relays IS NOT powered and 1 means it IS
    powered. Relays are read from left to right, so it would look something along the lines of:
     1   2   3   4   5   6   7   8   9   10
    [__, __, __, __, __, __, __, __, __, __]
    """
    # safe state - all valves unpowered
    SAFE_STATE = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    # closed state - all valves closed
    CLOSED_STATE = [0, 0, 0, 0, 1, 0, 1, 0, 0, 0]
#    CLOSED_STATE = [1, 1, 1, 1, 0, 0, 0, 0, 0, 1]
    GPIO_MAPPING = [4, 17, 27, 22, 10, 9, 11, 5, 6, 13]

    def __init__(self, GPIO):
        self._armed = False
        for pin in self.GPIO_MAPPING:
            GPIO.setup(pin, GPIO.OUT)
            # GPIO.output(pin, GPIO.LOW)
        self._state = self.CLOSED_STATE
        self._requested_state = self._state.copy()
        """
        SCR_tag tracks what triggered latest state change request. Meaning of each SCR_tag value:
        000 - Current state is that of the request from the user
        001 - Current state is a result of rejecting the request
        010 - Redline-commanded state
        011 - Auto-safing state
        100 -
        101 -
        110 -
        111 -
        """
        self._SCR_tag = 0

    def arm(self):
        self._armed = True
        logging.info("ARMED")

    def disarm(self):
        self._armed = False
        logging.info("DISARMED")

    def is_armed(self):
        return self._armed

    def get_state(self):
        return self._state

    def get_telemetry(self):
        # Convert bit array of states into number
        states = Utils.num(self._state)

        telemObject = {
            "pc_soft_armed" : self.is_armed(),
            "pc_state": states,
            "pc_scr_tag": self._SCR_tag
        }
        return telemObject

    def request_state(self, request, tag):
        self._requested_state = request.copy()
        self._SCR_tag = tag

    def INITIATE_FIRE_SEQUENCE(self, GPIO):
        if (self._armed):
            GPIO.output(self.GPIO_MAPPING[9], GPIO.HIGH)
            time.sleep(1)
            GPIO.output(self.GPIO_MAPPING[7], GPIO.HIGH)
            GPIO.output(self.GPIO_MAPPING[8], GPIO.HIGH)
            time.sleep(9)
            GPIO.output(self.GPIO_MAPPING[9], GPIO.LOW)
            time.sleep(60)
            GPIO.output(self.GPIO_MAPPING[7], GPIO.LOW)
            GPIO.output(self.GPIO_MAPPING[8], GPIO.LOW)

    def set_safe_state(self, tag):
        """
        Set to relays to safe state and update SCR tag with given tag.
        """
        self._requested_state = self.SAFE_STATE
        self._SCR_tag = tag
        self.update() # !!! need to pass in gpio, which this class doesn't own....

    def update(self, GPIO):
        """
        Update current relays states upon a change to _requested_state. We only update the state if
        the change is valid and when the relays are armed.
        """
        if (self._requested_state != self._state):
            if (self._armed):
                update_validity = self.check_safe_update()
                print("Validity: ", update_validity[0])
                if update_validity[0]:
                    for idx, relay_state in enumerate(self._requested_state):
                        if relay_state == 1:
                            GPIO.output(self.GPIO_MAPPING[idx], GPIO.HIGH)
                        else:
                            GPIO.output(self.GPIO_MAPPING[idx], GPIO.LOW)
                    self._state = self._requested_state.copy()
                    logging.info("SCR by '" + str(self._SCR_tag) + "' approved to " + str(self._state))
                else:
                    self._requested_state = self._state.copy()
                    logging.info("INVALID STATE REQUEST, ignoring request." + update_validity[1])
            else:
                self._requested_state = self._state.copy()
                logging.info("DISARMED, ignoring SCR.")

    def check_safe_update(self):
        """
        Make sure we are not entering a prohibited state according to configuration files.
        """
        # initialize dicitionaries that will hold json file contents and read them in
        relay_map = {}
        prohibited_states = {}
        with open("relay_map.json") as relays_f:
            relay_map = json.load(relays_f)

        with open("prohibited_states.json") as states_f:
            prohibited_states = json.load(states_f)

        # check for states we know must be mutually exclusive
        for mutex in prohibited_states["mutual_exclusions"]:
            if (self._requested_state[relay_map[mutex[0]]] & self._requested_state[relay_map[mutex[1]]]):
                return (False, "Mutual exclusion violation for {} and {}.".format(mutex[0], mutex[1]))

        return (True, "")
