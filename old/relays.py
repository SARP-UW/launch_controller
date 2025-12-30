import time
import json
import logging
logging.basicConfig(level=logging.DEBUG)
from bitfield_utils import Utils
import pdb

class Relays:
    """
    Relay state management class. Here we handle logic for requested commands. States are
    represented using an array of 10 integers. 0 means the relays IS NOT powered and 1 means it IS
    powered. Relays are read from left to right, so it would look something along the lines of:
     1   2   3   4   5   6   7   8   9   10
    [__, __, __, __, __, __, __, __, __, __]
    """

    GPIO_MAPPING = [13, 6, 5, 11, 9, 10, 22, 27, 17, 4]

    def __init__(self, GPIO):
        # vent and closed state are both variable to the board it is on
        # vent state - all valves unpowered
        global VENT_STATE
        # closed state - all valves closed
        global CLOSED_STATE
        self._control = open("/home/pi/controller/control.txt", "r").read()[0:4]
        self._armed = True
        self._inj = False
        for pin in self.GPIO_MAPPING:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)

        request = []
        # for default state, fill is set to venting state
        if self._control == "fill":
            VENT_STATE = [0, 0, 0, 0, 0, 1, 0, 1, 1, 0]
            CLOSED_STATE = [1, 1, 1, 1, 1, 0, 1, 0, 0, 0]
            self._state = VENT_STATE
            request = CLOSED_STATE
        else:
            VENT_STATE = [0, 0, 1, 0, 1, 0, 0, 0, 0, 0]
            CLOSED_STATE = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
            self._state = VENT_STATE
            request = CLOSED_STATE

        self.request_state(request, 0)
        self.update(GPIO)
        self._armed = False
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
        print("---------------------------------- ARMED ----------------------------------")
        self._armed = True
        logging.info("ARMED")

    def disarm(self, GPIO):
        if (self._state != CLOSED_STATE):
                self.request_state(CLOSED_STATE, 0)
                self.update(GPIO)
                logging.info("Setting closed state")
        self._armed = False
        logging.info("DISARMED")

    def is_armed(self):
        return self._armed

    def get_state(self):
        return self._state

    def get_telemetry(self):
        # Convert bit array of states into number
        states = Utils.num(self._state)

        print("Relay state: ", self._state)

        telemObject = {
            f"{self._control[0]}c_soft_armed" : self.is_armed(),
            f"{self._control[0]}c_state": states,
            f"{self._control[0]}c_scr_tag": self._SCR_tag
        }
        return telemObject

    def request_state(self, request, tag):
        self._requested_state = request.copy()
        self._SCR_tag = tag

    def INITIATE_FIRE_SEQUENCE(self, GPIO):
            # Oxygen Main Valve (OMV): 5
            # Fuel Main Valve (FMV): 6
            # Oxygen Purge Valve (OPV): 7
            # Helium Bottle Valve (HBV: 8
            prop = self.GPIO_MAPPING

            if self._inj:
                GPIO.output(prop[5], GPIO.LOW)
                time.sleep(0.02)
                GPIO.output(prop[6], GPIO.LOW)
                self._inj = False
                return

            if not self._armed:
                return

            # Step 1: Fire button clicked- Power ignitor
            GPIO.output(prop["igniter"], GPIO.HIGH)
            time.sleep(3.5)

            # Step 2: Open OMV (Ox Main Valve)
            GPIO.output(prop[5], GPIO.HIGH)

            # Step 3: Delay 65 ms
            time.sleep(0.065)

            # Step 4: Open FMV (Fuel Main Valve)
            GPIO.output(prop[6], GPIO.HIGH)

            # Step 5: Delay 14.5 s (combustion duration)
            time.sleep(14.5)

            # Step 6: Open OPV (Ox Purge Valve)
            GPIO.output(prop[7], GPIO.HIGH)

            # Step 7: Delay 30 s (purge time)
            time.sleep(30)

            # Step 8: Close OPV
            GPIO.output(prop[7], GPIO.LOW)

            # Step 9: Close HBV (Helium Blowdown Valve)
            GPIO.output(prop[8], GPIO.LOW)

            # Step 10: Delay 30 s
            time.sleep(30)

            # Step 11: Close OMV
            GPIO.output(prop[5], GPIO.LOW)

            # Step 12: Close FMV
            GPIO.output(prop[6], GPIO.LOW)

            # Final: Power off ignitor
            GPIO.output(prop["igniter"], GPIO.LOW)
        
    def INITIATE_FIRE_SEQUENCE_OLD(self, GPIO):
        if (self._inj):
            GPIO.output(self.GPIO_MAPPING[5], GPIO.LOW)
            time.sleep(0.02)
            GPIO.output(self.GPIO_MAPPING[6], GPIO.LOW)
            self._inj = False
            return

        if (self._armed):
            #self._inj = True
            # power ignitor
            GPIO.output(self.GPIO_MAPPING[0], GPIO.HIGH)
            # delay 2000 ms
            time.sleep(3.5)
            # open solenoid (injector)
            GPIO.output(self.GPIO_MAPPING[5], GPIO.HIGH)  # OX
            time.sleep(0.0055) # NOTE: NEED TO ENSURE 65 ms DELAY HERE
            GPIO.output(self.GPIO_MAPPING[6], GPIO.HIGH)  # FUEL
            # delay 30 ms
            #time.sleep(0.5)
            # close solenoid (injector)
            time.sleep(8.5)
            GPIO.output(self.GPIO_MAPPING[5], GPIO.LOW)
            GPIO.output(self.GPIO_MAPPING[6], GPIO.LOW)
            # delay 5 seconds before we power off the ignitor
            GPIO.output(self.GPIO_MAPPING[0], GPIO.LOW)
        return

    def PULSE_VALVE(self, GPIO, valve, delay):
        # flip requested valve
        self._requested_state[valve] = 0 if self._requested_state[valve] == 1 else 1
        self.update(GPIO)
        # valve delay
        time.sleep(delay/1000)
        # flip to previous state
        self._requested_state[valve] = 0 if self._requested_state[valve] == 1 else 1
        self.update(GPIO)

    def SET_VENT_STATE(self, GPIO, tag):
        """
        Set to relays to safe state and update SCR tag with given tag.
        """
        self.request_state(VENT_STATE, tag)
        self.update(GPIO)
        time.sleep(0.5)
        self._requested_state[1] = not self._requested_state[1]
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
            if (True):
                update_validity = self.check_safe_update()
                print("Validity: ", update_validity[0])
                if update_validity[0]:
                    for idx, relay_state in enumerate(self._requested_state):
                        print()
                        print("Requested state: ", self._requested_state)
                        print("Relay state: ", relay_state)
                        print()
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
        relay_map = {}
        prohibited_states = {}
        with open("/home/pi/controller/" + self._control + "_relay_map.json") as relays_f:
            relay_map = json.load(relays_f)

        with open(f"/home/pi/controller/{self._control}_prohibited_states.json") as states_f:
            prohibited_states = json.load(states_f)

        # check for states we know must be mutually exclusive
        for mutex in prohibited_states["mutual_exclusions"]:
            if (self._requested_state[relay_map[mutex[0]]] & self._requested_state[relay_map[mutex[1]]]):
                return (False, "Mutual exclusion violation for {} and {}.".format(mutex[0], mutex[1]))

         # check for states we know must be mutually inclusive
        for mutex in prohibited_states["mutual_inclusions"]:
            if (self._requested_state[relay_map[mutex[0]]]):
                # if relay with mutual inclusion req requested open
                if (self._requested_state[relay_map[mutex[0]]] != self._requested_state[relay_map[mutex[1]]]):
                  # mutual inclusion requirement not met
                  return (False, "Mutual inclusion violation for {} and {}.".format(mutex[0], mutex[1]))
        """
        return (True, "")
