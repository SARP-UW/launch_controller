# Mock GPIO module for testing on non-Raspberry Pi environments

# Constants
BCM = 'BCM'
OUT = 'OUT'
LOW = 'LOW'
HIGH = 'HIGH'

def setmode(mode):
    print(f"GPIO mode set to {mode}")

def setup(pin, mode):
    print(f"GPIO pin {pin} set up as {mode}")

def output(pin, state):
    print(f"GPIO pin {pin} set to {state}")

def cleanup():
    print("GPIO cleanup called")
