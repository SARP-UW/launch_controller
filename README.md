# Launch Controller

<<<<<<< HEAD
Software architecture for Launch Controller Ground System Operations.

## Virtual Environment

This virtual environment will ensure that this code runs with minimal issues on any system.

### How to Use

The following script simplifies the setup/activation process. Navigate to this root folder in the terminal and execute the following:

```bash
source venv.sh
```

This will do up to three things:
1. The specified virtual environment will be created if it does not exist.
2. The virtual environment will be activated.
3. The dependencies needed for this code to execute properly will be installed.

### Adding Dependencies

To add a dependency to this project, just add the name of the dependency to the `requirements.txt` file and run

```bash
source venv.sh
``` 

again to update the virtual environment.

### Troubleshooting

Make sure and execute this script from the root directory.

If this script does not execute as expected, double check that pip3 is installed.

If python isn't detecting the dependencies in the virtual environment or if the virtual environment did not exist prior to executing this script, then restart the terminal session after this script has finished running and execute it again to activate the virtual environment.
=======
Software architecture for Launch Controller Ground System Operations at SARP-UW

## Usage
1. Install all the necessary dependencies 
2. Execute `controller.py` to start the system

## Software Architecture
1. *Controller*:
This is the main class responsible for managing the operations.
It initializes the relays, sensors, network nodes and controls the event loop.

2. *Relays*: 
This manages the state of relays which control valves and igniters.


3. *Sensors*:
This collects telemetry data from various sensors; pressure and CPU temp

4. *Telemetry and Command Codecs*:
Handle the encoding and decoding of telemetry and command messages.

5. *Network Nodes*:
Manage the sending and receiving of data over the network.
`SendNode` and `RecieveNode` classes are used for communication with ground control.

## Configuration:
The System relies on `gse_master.json` file, therefore ensure it is present in the directory.

## Testing:
Unit Tests are provided in tests directory which can be run usin `pytest`
For more test related details refer to tests/README.md
>>>>>>> origin/development
