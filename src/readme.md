# Src Directory
This directory contains the code for the launch controller system's backend server (written in python).

## Content
- settings.py: Contains global constants which dictate the behavior/output of the program.
- logger.py: Contains the "Logger" class used for logging data to files.
- pressure_sensor.py: Contains the "PressureSensor" class used for reading data from pressure sensors (through the ADC).
- valve.py: Contains the "Valve" class used for controlling valves connected to the system.
- controller.py: Contains the "Controller" class used for controlling valves, periodically reading pressure sensor data and logging the resulting data to files.
- website.py: Contains the "website" class which hosts the flask server (and API) for the website/UI.