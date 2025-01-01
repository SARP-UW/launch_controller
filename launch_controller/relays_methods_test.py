from relays import Relays

try:
    import RPi.GPIO as GPIO
except (RuntimeError, ModuleNotFoundError):
    # If theres an issue imports spoof GPIO library
    print("Spoofing GPIO.")
    import fake_rpigpio.utils
    fake_rpigpio.utils.install()
    import RPi.GPIO as GPIO

relays = Relays(GPIO)
config_path = "gse_master.json"

print(f"\n\nBegin tests:")

print(f"\nload_config(): ", end=" ")
print(relays.load_config(config_path))

print(f"\nis_armed(): ", end=" ")
print(relays.is_armed())

print(f"\narm(): ", end=" ")
relays.arm(GPIO)

print(f"\nis_armed(): ", end=" ")
print(relays.is_armed())

print(f"\ndisarm(): ", end=" ")
relays.disarm(GPIO)

print(f"\nis_armed(): ", end=" ")
print(relays.is_armed())

print(f"\nget_state(): ", end=" ")
print(relays.get_state())

# FIRST: third key is overwriting the second key
# SECOND: change gse_master.json telemetry_config.p.psomething -> telemetry_config.prop.something (if it doesn't mess code up elsewhere)
print(f"\nget_telemetry(): ", end=" ")
print(relays.get_telemetry())

# SCR_tag tracks what triggered latest state change request. Meaning of each SCR_tag value:
#         000 - Current state is that of the request from the user
print(f"\nrequest_state(): ", end=" ")
print(relays.request_state(relays.get_state(), 0))

print(f"\narm(): ", end=" ")
relays.arm(GPIO)

print(f"\nINITIATE_FIRE_SEQUENCE():")
# relays.INITIATE_FIRE_SEQUENCE(GPIO)

print(f"\nPULSE_VALVE(): ")
print(relays.PULSE_VALVE(GPIO, valve=0, delay=1000))

print(f"\nSET_VENT_STATE(): ")
print(relays.SET_VENT_STATE(GPIO, 0))

print(f"\nSET_CLOSED_STATE(): ")
print(relays.SET_CLOSED_STATE(GPIO, 0))

print(f"\nupdate(): ")
print(relays.update(GPIO))