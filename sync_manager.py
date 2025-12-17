import os
import json
import datetime

SYNC_RECORD_FILE = "asana_sync_record.json"


class SyncManager:
    def __init__(self, filename=SYNC_RECORD_FILE):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.filename = os.path.join(script_dir, filename)
        self.records = self._load()

    def _load(self):
        if os.path.exists(self.filename):
            try:
                with open(self.filename, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def get_last_sync(self, project_id):
        return self.records.get(str(project_id))

    def save_sync_time(self, project_id, timestamp_iso):
        self.records[str(project_id)] = timestamp_iso
        with open(self.filename, "w", encoding="utf-8") as f:
            json.dump(self.records, f, indent=2)
