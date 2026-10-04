"""Local configuration: paths, config.json, printer mappings, job log."""

import json
import os
import time

APP_DIR = os.path.expanduser("~/.config/uprint")
SPOOL_DIR = os.path.join(APP_DIR, "spool")
CONFIG_FILE = os.path.join(APP_DIR, "config.json")
PRINTERS_FILE = os.path.join(APP_DIR, "printers.json")
JOBS_LOG = os.path.join(APP_DIR, "jobs.log")

DEFAULT_CONFIG = {
    "client_id": "",
    "tenant": "common",
    "port": 8631,
}


def ensure_dirs():
    os.makedirs(APP_DIR, mode=0o700, exist_ok=True)
    os.makedirs(SPOOL_DIR, mode=0o700, exist_ok=True)


def load_config():
    ensure_dirs()
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            cfg.update(json.load(f))
    return cfg


def save_config(cfg):
    ensure_dirs()
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)
    os.chmod(CONFIG_FILE, 0o600)


def load_printers():
    ensure_dirs()
    if not os.path.exists(PRINTERS_FILE):
        return {}
    with open(PRINTERS_FILE) as f:
        return json.load(f)


def save_printers(mapping):
    ensure_dirs()
    with open(PRINTERS_FILE, "w") as f:
        json.dump(mapping, f, indent=2)


def log_job(entry):
    ensure_dirs()
    entry = dict(entry)
    entry["at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(JOBS_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def read_jobs(limit=20):
    if not os.path.exists(JOBS_LOG):
        return []
    with open(JOBS_LOG) as f:
        lines = f.read().strip().split("\n")
    out = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out
