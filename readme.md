# Launch Controller
This repo contains the code for the SARP launch controllers (fill/prop controller). It 
allows users to control valves, read pressure sensors, and execute complex procedures
from a single unified UI (website).

## Usage

Create python virtual environment (optional):
```bash
python -m venv <VENV NAME>
```

Install required dependencies:
```bash
pip install -r requirements.txt
```

Run program (must use absolute paths to configuration files):
```bash
python3 main.py -c <CONTROLLER CONFIG PATH> -w <WEBSITE CONFIG PATH>
```

## Configuration Files
The launch controller program requires two seperate JSON configuration files. The controller configuration file specifies the configuration of the code running locally on the launch controller (i.e. data/state log files, pressure sensors, valves). The website configuration file specifies the configuration of the website/UI (website port, server status/error log files, procedures, invalid states). Example configuration files can be found in the config/default directory of this repository. 

### Controller Configuration File
The first element in the controller configuration file is the "general_config" section. This section contains general configuration information for the software running locally on the launch controller.
```json
"general_config":
{
    "pressure_sensor_data_rate": <Rate to read pressure sensors in Hz>,
    "controller_log_path": <Path to file where controller status/errors are logged>,
    "pressure_sensor_data_log_path": <Path to file where pressure sensor data is logged>,
    "valve_data_log_path": <Path to file where valve state information is logged>
}
```

The second element in the controller configuration file is the "pressure_sensor_config" section. This section contains a list of objects which each contain configuration information about a single pressure sensor which is connected to the system.
```json
"pressure_sensor_config":
[
    {
        "id": <Unique numerical ID for pressure sensor>,
        "name": <Name of pressure sensor>,
        "voltage_range": {
            "min": <Minimum voltage output by pressure sensor>,
            "max": <Maximum voltage output by pressure sensor>
        },
        "pressure_range": {
            "min": <Minimum pressure readable by pressure sensor>,
            "max": <Maximum pressure readable by pressure sensor>
        }
    },
    // Repeat above object for each pressure sensor connected to the system
]
```

The third element in the controller configuration file is the "valve_config" section. This section contains a list of objects which each contain configuration information about a single valve which is connected to the system.
```json
"valve_config":
[
    {
        "id": <Unique numerical ID for valve>,
        "name": <Name of valve>,
        "default_state": <Default (unpowered) state of valve: "open" or "closed">
    },
    // Repeat above object for each valve connected to the system
]
```

### Website Configuration File
The first element in the website configuration file is the "general_config" section. This section contains general configuration information for the website/UI.
```json
"general_config": {
    "website_title": <Title for website>,
    "website_log_path": <Path to file where website status/error information is logged>,
    "port": <Port where website is hosted>,
    "polling_rate": <Rate at which website users are queried to determine disconnections in Hz>,
    "heartbeat_timeout": <Duration between updates required for users to be marked disconnected>,
    "safe_state_timeout": <Duration before safe state activates after last user disconnection>
}
```

The second element in the website configuration file is the "invalid_valve_state" section. This section contains a list of objects which each contain lists of valve states which are considered to be invalid. When the user attempts to set valves into one of these states they will be shown a popup warning message on the website.
```json
"invalid_valve_states": [
    {
        // May be ommited if the invalid state does not require any open valves
        "open": <List of valve IDs [1, 2, ...] which when open result in the invalid state>,

        // May be ommited if the invalid state does not require any closed valves
        "closed": <List of valve IDs [1, 2, ...] which when closed result in the invalid state>
    }
    // Repeat for number of invalid valve states
]
```

The third element in the website configuration file is the "system_safe_states". This section contains a list of safe states for the system which will be automatically entered when a user safes the system or "safe mode" is on and no user has been connected to the website for the configured timeout. Each system safe state contains three fields - a name, a list of requirements, and a list of actions. The first safe state in the list which has its requirements satisfied will have its actions executed when the system is safed.
```json
"system_safe_states": [
    // Note: The first safe state (based on index in this list) to have all its requirements met will be executed.
    {
        "name": <Name of safe state>,
        "requirements": [
            // The following objects are types of requirements which can be included in this list.
            {
                "type": "pressure_above",
                "sensor_id": <ID of target pressure sensor>,
                "threshold": <Required minimum pressure of target sensor>
            },
            {
                "type": "pressure_below",
                "sensor_id": <ID of target pressure sensor>,
                "threshold": <Required maximum pressure of target sensor>
            },
            {
                "type": "pressure_between",
                "sensor_id": <ID of target pressure sensor>,
                "min_threshold": <Required minimum pressure of target sensor>,
                "max_threshold": <Required maximum pressure of target sensor>
            },
            {
                "type": "valve_state",
                "valve_id": <ID of target valve>,
                "state": <Required valve state ("open" or "closed")>
            }
        ],
        "actions": [
            // The following objects are types of actions which can be included in this list
            // Note: actions are executed in the order they are found in this list
            // Note: actions contained within a list will be executed simultaneously
            {
                "type": "set_valve",
                "valve_id": <ID of target valve>,
                "state": <State to set valve to ("open" or "closed")> 
            },
            {
                // Toggles the state of the valve for the specified duration
                "type": "pulse_valve",
                "valve_id": <ID of target valve>,
                "duration": <Duration of pulse in seconds>
            },
            {
                "type": "wait",
                "duration": <Duration to wait>
            }
        ]
    },
    // Repeat above object for each system safe state
]
```

The final element in the website configuration file is the "procedures" section. This section contains a list of procedures which contain steps that can be executed by users on the website. Each procedure is represented as an object in the procedures list which contain a 'name' field and a 'steps' field. The 'steps' field is a list of steps which constitute the procedure. Each step itself contains three seperate subfields - the procedure name, requirements, and actions.
```json
"procedures": [
    {
        "name": <Name of procedure>,
        "steps": [
            // Order of steps in list is the order they are expected to be executed in.
            {
                "name": <Name of safe state>,
                "requirements": [
                    // The following objects are types of requirements which can be included in this list.
                    {
                        "type": "pressure_above",
                        "sensor_id": <ID of target pressure sensor>,
                        "threshold": <Required minimum pressure of target sensor>
                    },
                    {
                        "type": "pressure_below",
                        "sensor_id": <ID of target pressure sensor>,
                        "threshold": <Required maximum pressure of target sensor>
                    },
                    {
                        "type": "pressure_between",
                        "sensor_id": <ID of target pressure sensor>,
                        "min_threshold": <Required minimum pressure of target sensor>,
                        "max_threshold": <Required maximum pressure of target sensor>
                    },
                    {
                        "type": "valve_state",
                        "valve_id": <ID of target valve>,
                        "state": <Required valve state ("open" or "closed")>
                    }
                    {
                        "type": "custom_message",
                        "message": <Desired message to display in step requirements>
                    }
                ],
                "actions": [
                    // The following objects are types of actions which can be included in this list
                    // Note: actions are executed in the order they are found in this list
                    // Note: actions contained within a list will be executed simultaneously
                    {
                        "type": "set_valve",
                        "valve_id": <ID of target valve>,
                        "state": <State to set valve to ("open" or "closed")> 
                    },
                    {
                        // Toggles the state of the valve for the specified duration
                        "type": "pulse_valve",
                        "valve_id": <ID of target valve>,
                        "duration": <Duration of pulse in seconds>
                    },
                    {
                        "type": "wait",
                        "duration": <Duration to wait>
                    }
                ]
            }
            // Repeat above object for each step in procedure
        ]
    }
    // Repeat above object for each desired procedure
]
```


