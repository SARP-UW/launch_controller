from fillcontroller import FillController
import time
import logging
logging.basicConfig(level=logging.DEBUG)
try:
    import RPi.GPIO as GPIO
except (RuntimeError, ModuleNotFoundError):
    print("Spoofing GPIO.")
    import fake_rpigpio.utils
    fake_rpigpio.utils.install()
    import RPi.GPIO as GPIO

class TestFillController:
    def get_harness(self):
        return FillController()

    # Tests standard operation of relays via State Change Request
    def test_relays(self):
        fc = self.get_harness()
        fc.relays.arm()
        stateChangeRequest = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        initialState = stateChangeRequest.copy()
        for idx, relay in enumerate(stateChangeRequest):
            stateChangeRequest[idx] = 1
            firstLoopRequest = stateChangeRequest.copy()
            fc.relays.request_state(stateChangeRequest, "testA")
            print(stateChangeRequest)
            #assert(fc.relays.get_state() == initialState)
            #assert(fc.relays._requested_state == stateChangeRequest)
            #assert(fc.relays.SCR_tag == "testA")
            fc.relays.update(GPIO)
            #assert(fc.relays.get_state() == stateChangeRequest)
            #assert(fc.relays._requested_state == stateChangeRequest)
            #assert(fc.relays.SCR_tag == "testA")
            time.sleep(.1)
            stateChangeRequest[idx] = 0
            fc.relays.request_state(stateChangeRequest, "testB")
            #assert(fc.relays.get_state() == firstLoopRequest)
            #assert(fc.relays._requested_state == stateChangeRequest)
            #assert(fc.relays.SCR_tag == "testB")
            fc.relays.update(GPIO)
            #assert(fc.relays.get_state() == stateChangeRequest)
            #assert(fc.relays._requested_state == stateChangeRequest)
            #assert(fc.relays.SCR_tag == "testB")
            time.sleep(.1)
        fc.relays.request_state([1, 0, 0, 0, 1, 1, 1, 0, 0, 0], 1)
        fc.relays.update(GPIO)
        
