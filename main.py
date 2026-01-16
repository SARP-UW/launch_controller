import json
import argparse
import os
import subprocess
import time
import socket
from src.controller import Controller
import src.settings as settings
from src.website import ControllerWebsite

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
        default=f'{os.path.dirname(__file__)}/config/default/controller_config.json',
        help='Path to controller configuration file (default: config/default/controller_config.json)'
    )
    parser.add_argument(
        '-w', '--website_config',
        type=str,
        default=f'{os.path.dirname(__file__)}/config/default/website_config.json',
        help='Path to website configuration file (default: config/default/website_config.json)'
    )
    args = parser.parse_args()
    
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
    website = None
    try:
        if settings.VERBOSE_SYS_MODE:
            print(f"SYSTEM STATUS: Initializing controller from config: {args.controller_config}")
        controller_config = load_config(args.controller_config)
        controller = Controller.from_config(config = controller_config)

        if settings.VERBOSE_SYS_MODE:
            print(f"SYSTEM STATUS: Initializing website from config: {args.website_config}")
        website_config = load_config(args.website_config)
        website = ControllerWebsite.from_config(controller = controller, config = website_config)        
        print(f"SYSTEM STATUS: System running!")
        print(f"SYSTEM STATUS: Website at: http://{_get_ip_str()}:{website_config['general_config']['port']}")
    
        while True:
            time.sleep(1)
    
    except KeyboardInterrupt:
        print("\nSYSTEM STATUS: Stopping system...")
        if website:
            website.shutdown()
        if controller:
            controller.shutdown()

if __name__ == "__main__":
    main()