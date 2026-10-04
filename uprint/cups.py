"""
Driverless printing on macOS, wrapped for the terminal.

Everything here uses macOS's built-in CUPS + IPP Everywhere support:
no printer drivers to download, no accounts, no cloud. `-m everywhere`
tells CUPS the printer speaks driverless IPP, which every AirPrint /
modern network printer does.
"""

import os
import re
import subprocess


def _run(cmd, need_root=False):
    if need_root and os.geteuid() != 0:
        cmd = ["sudo", "-p", "Password for %u (needed once to install the printer): "] + cmd
    print("+ " + " ".join(cmd))
    subprocess.run(cmd, check=True)


def install_printer(local_name, device_uri, description=""):
    """Install a driverless queue. Needs admin once (sudo)."""
    cmd = ["lpadmin", "-p", local_name, "-E", "-v", device_uri,
           "-m", "everywhere", "-o", "printer-is-shared=false"]
    if description:
        cmd += ["-D", description]
    _run(cmd, need_root=True)
    _run(["cupsenable", local_name], need_root=True)
    _run(["cupsaccept", local_name], need_root=True)
    print("Printer '%s' installed — it now appears in System Settings -> "
          "Printers & Scanners and in every app's print dialog." % local_name)


def remove_printer(local_name):
    _run(["lpadmin", "-x", local_name], need_root=True)
    print("Printer '%s' removed." % local_name)


def list_printers():
    """Return [(name, state)] from lpstat."""
    try:
        out = subprocess.run(["lpstat", "-p"], capture_output=True,
                             text=True, timeout=10).stdout
    except FileNotFoundError:
        return []
    printers = []
    for line in out.splitlines():
        m = re.match(r"^printer (\S+) (.*)$", line)
        if m:
            printers.append((m.group(1), m.group(2).strip()))
    return printers


def default_printer():
    try:
        out = subprocess.run(["lpstat", "-d"], capture_output=True,
                             text=True, timeout=10).stdout
    except FileNotFoundError:
        return None
    m = re.search(r"system default destination:\s*(\S+)", out)
    return m.group(1) if m else None


def print_file(printer, path):
    """Send a file to a printer via the system spooler (no login needed)."""
    if not os.path.exists(path):
        raise RuntimeError("file not found: %s" % path)
    cmd = ["lp"]
    if printer:
        cmd += ["-d", printer]
    cmd += [path]
    print("+ " + " ".join(cmd))
    subprocess.run(cmd, check=True)
    print("Sent to %s." % (printer or "default printer"))
