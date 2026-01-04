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

The second element in the website configuration file is the "invalid_valve_state" section. This section contains a list of valve states which are considered to be invalid. When the user attempts to set valves into one of these states they will be shown a popup warning message.

```json
// Format of list: [<valve ID>, <valve ID>]
"invalid_valve_states": [
    {
        // May be ommited if the invalid state does not require any open valves
        "open": <List of valve IDs which when open result in the invalid state>,

        // May be ommited if the invalid state does not require any closed valves
        "closed": <List of valve IDs which when closed result in the invalid state>
    }
]
```

The third element in the website configuration file is the "valve_safe_config"

