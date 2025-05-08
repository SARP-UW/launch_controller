import sys, os
sys.path.append(os.path.join(os.path.dirname(sys.path[0]), ''))
from fillcontroller import FillController
import time
import logging
import pytest
import itertools
logging.basicConfig(level=logging.DEBUG)
try:
    import RPi.GPIO as GPIO
except (RuntimeError, ModuleNotFoundError):
    print("Spoofing GPIO.")
    import fake_rpigpio.utils
    fake_rpigpio.utils.install()
    import RPi.GPIO as GPIO

mutual_exclusions = [
    (0,1),
    (0,2),
    (0,3),
    (1,2),
    (1,3),
    (2,3)
]
mutual_inclusions = [
    (0,4),
    (1,4),
    (2,6),
    (3,6)
]


class TestRelays:
    # Pytest does not allow user-defined __init__() function
    state_change_request = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]  # used in pytest parameterization only
    fc = FillController()
    test_cases = list(itertools.product([0, 1], repeat=10))

    @pytest.fixture
    def setup_harness(self):
        self.fc.relays.__init__(GPIO)
        self.fc.relays.arm()
        self.stateChangeRequest = [0, 0, 0, 0, 1, 0, 1, 0, 0, 0]
        self.initialState = [0, 0, 0, 0, 1, 0, 1, 0, 0, 0]  # closed state
        return self.fc, self.stateChangeRequest, self.initialState

    # Relay test A
    def relays_test_a(self, fc, stateChangeRequest, initialState):
        fc.relays.request_state(stateChangeRequest, "testA")
        print("Change request: ", stateChangeRequest)
        assert (fc.relays.get_state() == initialState)
        assert (fc.relays._requested_state == stateChangeRequest)
        assert (fc.relays._SCR_tag == "testA")
        fc.relays.update(GPIO)
        # Here we need both the stateChangeRequest and relays.get_state()
        # Use stateChangeRequest to confirm that the fill controller has caught errors correctly.
        open_relays_idx = [index for index, elem in enumerate(stateChangeRequest) if elem == 1]
        current_state = fc.relays.get_state()

        # mutual exclusions
        for exc in mutual_exclusions:
            if (all(x in open_relays_idx for x in exc)):
                assert (current_state != stateChangeRequest)
        # mutual inclusions
        for inc in mutual_inclusions:
            if (not all(x in open_relays_idx for x in inc)):
                assert (current_state == stateChangeRequest)
        time.sleep(.1)

    # Tests standard operation of relays via State Change Request
    # Uses Pytest parametrization syntax:
    # https://docs.pytest.org/en/reorganize-docs/parametrize.html#parametrize
    @pytest.mark.parametrize("case", test_cases)
    def test_relay_2(self, setup_harness, case):
        fc, stateChangeRequest, initialState = setup_harness
        stateChangeRequest = list(case)
        self.relays_test_a(fc, stateChangeRequest, initialState)


class TestFillcontroller:
    @pytest.fixture
    def setup_controller(self):
        fc = FillController()
        return fc

    def test_processRequest(self, setup_controller):
        fc = setup_controller
        assert (fc.cmdReceiver != None)

    def test_checkRedlines(self, setup_controller):
        fc = setup_controller
        command, addr = fc.cmdReceiver.receive()
        assert (command["fc_redlines_armed"] == False)

    def test_updateActuators(self):
        assert ("Nothing to test here")
        pass
    
    def test_sendTelemetry(self):
        assert ("Nothing to test here")
        pass

    def test_checkNetwork(self):
        assert ("Nothing to test here")
        pass
