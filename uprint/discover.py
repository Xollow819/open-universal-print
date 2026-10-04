"""
Find printers on the local network via Bonjour/mDNS, using macOS's
built-in `dns-sd` tool. No login, no cloud, no drivers involved.

We browse the standard printer service types:
  _ipp._tcp     modern driverless printers (IPP Everywhere / AirPrint)
  _ipps._tcp    same, over TLS
  _printer._tcp classic LPD / JetDirect printers
"""

import re
import subprocess
import urllib.parse

SERVICE_TYPES = ["_ipp._tcp", "_ipps._tcp", "_printer._tcp"]

# dns-sd -B output line, e.g.:
# 19:12:33.456  Add  3  6 local.  _ipp._tcp.  My Office Printer
_BROWSE_LINE = re.compile(
    r"^\S+\s+Add\s+\d+\s+\d+\s+\S+\s+(\S+?)\.?\s+(.+?)\s*$"
)


def browse(service_type, domain="local", timeout=5):
    """Return instance names advertising service_type (deduped, sorted)."""
    try:
        proc = subprocess.run(
            ["dns-sd", "-B", service_type, domain],
            capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError:
        raise RuntimeError("dns-sd not found (expected on macOS)")
    except subprocess.TimeoutExpired as e:
        out = e.stdout or ""
        err = e.stderr or ""
        if isinstance(out, bytes):
            out = out.decode("utf-8", "replace")
        if isinstance(err, bytes):
            err = err.decode("utf-8", "replace")
        out = out + err
    else:
        out = proc.stdout
    found = []
    for line in out.splitlines():
        m = _BROWSE_LINE.match(line.strip())
        if m and service_type in m.group(1):
            name = m.group(2).strip()
            if name not in found:
                found.append(name)
    return sorted(found)


def discover(timeout=5):
    """Return [(instance_name, service_type, device_uri)]."""
    results = []
    for stype in SERVICE_TYPES:
        try:
            names = browse(stype, timeout=timeout)
        except RuntimeError:
            raise
        except Exception:
            continue
        for name in names:
            uri = "dnssd://%s.%s.local" % (
                urllib.parse.quote(name, safe=""), stype)
            results.append((name, stype, uri))
    # dedupe by instance name, preferring _ipp(s) over _printer
    seen = {}
    for name, stype, uri in results:
        if name not in seen or "_printer" in seen[name][0]:
            seen[name] = (stype, uri)
    return [(n, s, u) for n, (s, u) in sorted(seen.items())]


def guess_uri(ref):
    """
    Turn user input into a CUPS device URI.
      ipp://... / ipps://... / dnssd://... / lpd://... -> as-is
      192.168.1.10 / printer.lan                       -> ipp://host/ipp/print
      "My Office Printer" (with spaces)                -> dnssd://..._ipp._tcp.local
    """
    ref = ref.strip()
    if "://" in ref:
        return ref
    if " " in ref:
        return "dnssd://%s._ipp._tcp.local" % urllib.parse.quote(ref, safe="")
    return "ipp://%s/ipp/print" % ref
