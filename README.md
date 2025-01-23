# Launch Controller

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