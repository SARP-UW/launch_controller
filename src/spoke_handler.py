from typing import Dict
from src.valve import ValveState
from src.controller import Controller

class SpokeHandler:
  def __init__(self, controller: Controller):
    self.controller = controller

  def set_valve(self, args: Dict):
    print(args)
    valve_id = int(args.get("id"))
    state_str = args.get("state", "").lower()
    state = ValveState.OPEN if state_str == "open" else ValveState.CLOSED
    self.controller.set_valve(valve_id, state)