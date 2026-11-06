import time
from typing import Dict
from src.valve import ValveState
from src.controller import Controller

class SpokeHandler:
  def __init__(self, controller: Controller):
    self._controller = controller

  def set_valve(self, args: Dict):
    valve_id = int(args.get("valve_id"))
    state_str = args.get("state", "").lower()
    state = ValveState.OPEN if state_str == "open" else ValveState.CLOSED
    self._controller.set_valve(valve_id, state)

  def pulse_valve(self, args: Dict):
    valve_id = int(args.get("valve_id"))
    duration = float(args.get("duration", 1.0))
    self._controller.pulse_valve(valve_id, duration)
    time.sleep(duration)

  def wait(self, args: Dict):
    duration = float(args.get("duration", 1.0))
    time.sleep(duration)
    