"""
macOS integration: install/uninstall CUPS queues pointing at the local
IPP server, so printers appear in System Settings -> Printers & Scanners
and in every application's print dialog.

No Apple Developer account, no system extensions, no entitlements needed:
a CUPS queue is just configuration, and lpadmin is the supported tool for it.
"""

import os
import subprocess

LAUNCH_AGENT_LABEL = "dev.openuprint.serve"
LAUNCH_AGENT_PATH = os.path.expanduser(
    "~/Library/LaunchAgents/%s.plist" % LAUNCH_AGENT_LABEL)


def _run(cmd, need_root=False):
    """Run a command; prefix sudo when root is required and we lack it."""
    if need_root and os.geteuid() != 0:
        cmd = ["sudo"] + cmd
    print("+ " + " ".join(cmd))
    subprocess.run(cmd, check=True)


def printer_exists(name):
    r = subprocess.run(["lpstat", "-p", name],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return r.returncode == 0


def install_printer(local_name, port=8631, description=""):
    """Create a CUPS queue 'local_name' backed by our IPP server."""
    uri = "ipp://127.0.0.1:%d/printers/%s" % (port, local_name.replace(" ", "%20"))
    cmd = ["lpadmin", "-p", local_name, "-E", "-v", uri,
           "-m", "everywhere", "-o", "printer-is-shared=false"]
    if description:
        cmd += ["-D", description]
    _run(cmd, need_root=True)
    _run(["cupsenable", local_name], need_root=True)
    _run(["cupsaccept", local_name], need_root=True)
    print("Printer '%s' installed. It now appears in System Settings "
          "-> Printers & Scanners." % local_name)


def uninstall_printer(local_name):
    _run(["lpadmin", "-x", local_name], need_root=True)
    print("Printer '%s' removed." % local_name)


def install_autostart(python_exe, script_path, port=8631):
    """Keep `uprint serve` running via a user LaunchAgent (no entitlements)."""
    plist = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{python}</string>
    <string>{script}</string>
    <string>serve</string>
    <string>--port</string>
    <string>{port}</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>{home}/.config/uprint/serve.log</string>
  <key>StandardErrorPath</key><string>{home}/.config/uprint/serve.log</string>
</dict>
</plist>
""".format(label=LAUNCH_AGENT_LABEL, python=python_exe, script=script_path,
           port=port, home=os.path.expanduser("~"))
    os.makedirs(os.path.dirname(LAUNCH_AGENT_PATH), exist_ok=True)
    with open(LAUNCH_AGENT_PATH, "w") as f:
        f.write(plist)
    subprocess.run(["launchctl", "load", LAUNCH_AGENT_PATH], check=False)
    print("Autostart installed: uprint serve will run at login.")


def uninstall_autostart():
    subprocess.run(["launchctl", "unload", LAUNCH_AGENT_PATH], check=False)
    if os.path.exists(LAUNCH_AGENT_PATH):
        os.remove(LAUNCH_AGENT_PATH)
    print("Autostart removed.")
