import json
import logging

class config_util:
    def load_config(self, config_path):
        # Load configuration from a JSON file
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Error loading config file: {e}")
            return None