import os
import json

DATA_DIR = os.path.join(os.path.expanduser("~"), ".f2l_downloader")
os.makedirs(DATA_DIR, exist_ok=True)

SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
DOWNLOADS_FILE = os.path.join(DATA_DIR, "downloads.json")
DEFAULT_DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads")

class SettingsManager:
    def __init__(self):
        self.default_settings = {
            "download_folder": DEFAULT_DOWNLOAD_DIR,
            "default_connections": 8,
            "theme": "dark",
            "auto_start": True,
            "retry_attempts": 3,
            "notifications": True
        }
        self.settings = self.load()

    def load(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    res = self.default_settings.copy()
                    res.update(data)
                    return res
            except Exception:
                pass
        return self.default_settings.copy()

    def save(self):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def get(self, key, default=None):
        return self.settings.get(key, default if default is not None else self.default_settings.get(key))

    def set(self, key, value):
        self.settings[key] = value
        self.save()


class DownloadStorage:
    def __init__(self):
        pass

    def load(self):
        if os.path.exists(DOWNLOADS_FILE):
            try:
                with open(DOWNLOADS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def save(self, items):
        try:
            with open(DOWNLOADS_FILE, "w", encoding="utf-8") as f:
                json.dump(items, f, indent=2)
        except Exception as e:
            print(f"Error saving downloads: {e}")
