import sys
from pathlib import Path


class Utils:
    def __init__(self):
        self.config_path = self._get_config_path()

    @staticmethod
    def _get_config_path():
        home = Path.home()
        if sys.platform == "win32":
            base_dir = home / "AppData" / "Roaming" / "SifaPedal"
        elif sys.platform == "darwin":
            base_dir = home / "Library" / "Application Support" / "SifaPedal"
        else:
            base_dir = home / ".config" / "SifaPedal"

        base_dir.mkdir(parents=True, exist_ok=True)
        return str(base_dir / "config.json")
