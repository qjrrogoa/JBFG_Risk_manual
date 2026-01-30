import json
import os
import uuid
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE = os.path.join(BASE_DIR, "log", "chat_logs.json")

def ensure_log_file():
    """Ensures the log file exists and initializes it if necessary."""
    log_dir = os.path.dirname(LOG_FILE)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=4)

def load_logs():
    """Loads existing logs from the JSON file."""
    ensure_log_file()
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []

def save_log(entry):
    """Appends a new log entry to the JSON file."""
    logs = load_logs()
    logs.append(entry)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=4)

def update_log_feedback(log_id, is_bad):
    """Updates the 'bad' status of a specific log entry by ID."""
    logs = load_logs()
    updated = False
    for entry in logs:
        if entry.get("id") == log_id:
            entry["bad"] = is_bad
            updated = True
            break
    
    if updated:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=4)

def create_log_entry(question, answer, sources):
    """Creates a dictionary for a new log entry."""
    return {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "question": question,
        "answer": answer,
        "sources": sources,
        "bad": False
    }
