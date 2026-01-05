###################################################################################################
# Website Settings
###################################################################################################

# The rate (in Hz) at which the website update thread runs
WEBSITE_THREAD_UPDATE_RATE: float = 20.0

# The time (in seconds) after which a user is considered disconnected if no heartbeat is received
WEBSITE_HEARTBEAT_TIMEOUT: float = 3.0

###################################################################################################
# General System Settings
###################################################################################################

# If true, application runs in "mock" mode (simulates hardware interaction)
MOCK_MODE: bool = True

# If true, application prints valve state changes to console
PRINT_VALVE_STATES: bool = True

# If true, application prints pressure sensor readings to console
PRINT_PRESSURE_SENSOR_READINGS: bool = False

# If true, application prints controller status messages to console.
PRINT_CONTROLLER_STATUS: bool = False

# If true, application prints controller error messages to console.
PRINT_CONTROLLER_ERRORS: bool = True

# If true, application prints website status messages to console.
PRINT_WEBSITE_STATUS: bool = False

# If true, application prints website error messages to console.
PRINT_WEBSITE_ERRORS: bool = True

# If true, application prints Flask/Werkzeug HTTP request logs to console.
PRINT_FLASK_REQUESTS: bool = False

# If true, application prints verbose system mode messages to console.
VERBOSE_SYS_MODE: bool = False