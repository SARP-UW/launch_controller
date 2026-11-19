import json
import argparse
import logging
import os
import time
import socket
from spoke import Spoke
from src.controller import Controller
import src.settings as settings
from src.operations import ControllerOperations
from src.spoke_handlers import make_handlers
from src.telemetry import build_telemetry
from src.website import ControllerWebsite

# Spoke node id used when neither --node_id nor general_config.node_id (website config) is set.
DEFAULT_NODE_ID = 'launch_controller'

# Telemetry publish rate limits (Hz). Sensors can be read much faster; publishing every read would flood the hub.
DEFAULT_TELEMETRY_RATE = 10.0
MAX_TELEMETRY_RATE = 50.0

# Minimum seconds between repeated telemetry error messages, so a persistent failure doesn't spam the console.
TELEMETRY_ERROR_PRINT_INTERVAL = 5.0

def _get_ip_str() -> str:
    """
    Gets the IP address of this device as a string or <device ip> if unknown.
    This is some stack overflow magic - no idea how it works
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            if ip and not ip.startswith('127.'):
                return ip
        finally:
            s.close()
    except Exception:
        pass

    return "<device ip>"

def main():
    """
    Main entry point for program.
    """
    parser = argparse.ArgumentParser(
        description='Ground Control System - Valve and Sensor Management',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=
            """
            Example usage:
            python main.py --controller_config config/controller.json --website_config config/website.json
            python main.py -c controller_config.json -w website_config.json
            """
    )
    parser.add_argument(
        '-c', '--controller_config',
        type=str,
        default=f'{os.path.dirname(__file__)}/config/example/controller_config.json',
        help='Path to controller configuration file (default: config/example/controller_config.json)'
    )
    parser.add_argument(
        '-w', '--website_config',
        type=str,
        default=f'{os.path.dirname(__file__)}/config/example/website_config.json',
        help='Path to website configuration file (default: config/example/website_config.json)'
    )
    parser.add_argument(
        '--node_id',
        type=str,
        default=None,
        help=f'Spoke node id; must be unique per hub (default: general_config.node_id in website config, else {DEFAULT_NODE_ID})'
    )
    parser.add_argument(
        '--hub_addr',
        type=str,
        default=None,
        help='Hub address host:port (default: GSE_HUB_ADDR environment variable, else localhost:50051)'
    )
    parser.add_argument(
        '--telemetry_rate',
        type=float,
        default=DEFAULT_TELEMETRY_RATE,
        help=f'Telemetry publish rate in Hz (default: {DEFAULT_TELEMETRY_RATE})'
    )
    parser.add_argument(
        '--no_spoke',
        action='store_true',
        help='Do not connect to the hub (website only)'
    )
    args = parser.parse_args()
    if not 0 < args.telemetry_rate <= MAX_TELEMETRY_RATE:
        parser.error(f'--telemetry_rate must be in (0, {MAX_TELEMETRY_RATE}], got: {args.telemetry_rate}')

    # spoke.py reports connects, disconnects and failed commands through the logging module.
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(levelname)s: %(message)s')
    
    def load_config(config_path: str) -> dict:
        """
        Loads a JSON configuration file from the given path.
        """
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise json.JSONDecodeError(f"Invalid JSON in {config_path}: {e.msg}", e.doc, e.pos)

    print("SYSTEM STATUS: Starting system...")
    if settings.VERBOSE_SYS_MODE:
        print("SYSTEM STATUS: System settings:")
        print(f"  - MOCK_MODE = {settings.MOCK_MODE}")
        print(f"  - PRINT_VALVE_STATE = {settings.PRINT_VALVE_STATES}")
        print(f"  - PRINT_PRESSURE_SENSOR_READINGS = {settings.PRINT_PRESSURE_SENSOR_READINGS}")
        print(f"  - PRINT_WEBSITE_ERRORS = {settings.PRINT_WEBSITE_ERRORS}")
        print(f"  - PRINT_WEBSITE_STATUS = {settings.PRINT_WEBSITE_STATUS}")
        print(f"  - PRINT_CONTROLLER_ERRORS = {settings.PRINT_CONTROLLER_ERRORS}")
        print(f"  - PRINT_CONTROLLER_STATUS = {settings.PRINT_CONTROLLER_STATUS}")
    
    controller = None
    operations = None
    website = None
    spoke = None
    try:
        if settings.VERBOSE_SYS_MODE:
            print(f"SYSTEM STATUS: Initializing controller from config: {args.controller_config}")
        controller_config = load_config(args.controller_config)
        controller = Controller.from_config(config = controller_config)

        if settings.VERBOSE_SYS_MODE:
            print(f"SYSTEM STATUS: Initializing website from config: {args.website_config}")
        website_config = load_config(args.website_config)
        operations = ControllerOperations.from_config(controller = controller, config = website_config)
        website = ControllerWebsite.from_config(operations = operations, config = website_config)

        if not args.no_spoke:
            node_id = args.node_id or website_config['general_config'].get('node_id') or DEFAULT_NODE_ID
            if not isinstance(node_id, str):
                raise ValueError(f"Website config 'general_config.node_id' must be a string, got: {type(node_id).__name__}")
            spoke = Spoke(node_id, make_handlers(operations), hub_addr = args.hub_addr)
            spoke.start()

        print(f"SYSTEM STATUS: System running!")
        print(f"SYSTEM STATUS: Website at: http://{_get_ip_str()}:{website_config['general_config']['port']}")
        if spoke:
            print(f"SYSTEM STATUS: Spoke '{spoke.node_id}' connecting to hub at {spoke.hub_addr}, telemetry at {args.telemetry_rate} Hz")
        else:
            print(f"SYSTEM STATUS: Spoke disabled (--no_spoke)")

        _run_telemetry_loop(spoke, operations, args.telemetry_rate)

    except KeyboardInterrupt:
        pass
    finally:
        # Spoke first, so no hub command arrives halfway through shutting down the rest.
        print("\nSYSTEM STATUS: Stopping system...")
        if spoke:
            spoke.stop()
        if website:
            website.shutdown()
        if operations:
            operations.shutdown()
        if controller:
            controller.shutdown()

def _run_telemetry_loop(spoke: Spoke | None, operations: ControllerOperations, rate: float) -> None:
    """
    Publishes the full telemetry sample at a fixed rate until interrupted. With no spoke, just idles.
    Errors in one tick are printed (rate-limited) and never stop the loop.
    """
    if spoke is None:
        while True:
            time.sleep(1)

    period = 1.0 / rate
    next_tick = time.monotonic()
    last_error_print = float('-inf')
    while True:
        if spoke.connected:
            try:
                spoke.publish(build_telemetry(operations))
            except Exception as e:
                now = time.monotonic()
                if now - last_error_print >= TELEMETRY_ERROR_PRINT_INTERVAL:
                    print(f"SYSTEM ERROR: Failed to build telemetry: {type(e).__name__}: {e}")
                    last_error_print = now

        next_tick += period
        delay = next_tick - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        else:
            next_tick = time.monotonic()  # fell behind (e.g. a long stall); resync instead of bursting to catch up

if __name__ == "__main__":
    main()
