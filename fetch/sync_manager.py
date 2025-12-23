import os
import json

SYNC_RECORD_FILE = "asana_sync_record.json"


class SyncManager:
    def __init__(self, filename=SYNC_RECORD_FILE):
        # Store in the root of the project (parent of 'fetch' directory) or current working dir?
        # Let's keep it simple: relative to execution or fixed.
        # Original code used script_dir, which was the root.
        # Now script_dir is "fetch/". We want it in root.
        
        # Assumption: We run from root.
        # Or better: relative to constants in config?
        # Let's use config.BASE_DIR or just current CWD if we run main.py from root.
        # But to be safe let's put it in RAW_DIR or leave it in root.
        # User might want to see it easily. Let's put it in root.
        
        self.filename = os.path.abspath(filename)
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
