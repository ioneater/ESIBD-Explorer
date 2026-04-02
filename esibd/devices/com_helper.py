"""Helper to read COM port assignments from a central JSON file."""

import json
from pathlib import Path

COM_PORTS_FILE = Path(__file__).parent / 'com_ports.json'


def getComPort(device_key: str, default: int = 1) -> int:
    """Return the COM port number for *device_key* from com_ports.json.

    Falls back to *default* if the file or key is missing.
    """
    try:
        with open(COM_PORTS_FILE) as f:
            ports = json.load(f)
        return int(ports.get(device_key, default))
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return default
