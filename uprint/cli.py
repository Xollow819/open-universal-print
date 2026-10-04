"""uprint: open-source Universal Print client for macOS (terminal native)."""

import argparse
import os
import sys

from . import auth, config, cups, graph, server


def _client():
    cfg = config.load_config()
    if not cfg.get("client_id"):
        sys.exit("No client_id configured. Run: uprint login --client-id <APP_ID>")
    token = auth.get_access_token(tenant=cfg.get("tenant", "common"),
                                  client_id=cfg["client_id"])
    return graph.GraphClient(token), cfg


def cmd_login(args):
    cfg = config.load_config()
    if args.client_id:
        cfg["client_id"] = args.client_id
    if args.tenant:
        cfg["tenant"] = args.tenant
    if not cfg.get("client_id"):
        sys.exit("error: --client-id is required (Entra app registration -> "
                 "Application (client) ID)")
    config.save_config(cfg)
    auth.device_login(tenant=cfg.get("tenant", "common"),
                      client_id=cfg["client_id"])


def cmd_printers(_args):
    client, _cfg = _client()
    shares = client.list_shares()
    if not shares:
        print("No printer shares available to your account.")
        return
    print("%-38s  %s" % ("SHARE ID", "NAME"))
    for s in shares:
        print("%-38s  %s" % (s["id"], s.get("displayName", "?")))


def _resolve_share(client, ref):
    shares = client.list_shares()
    for s in shares:
        if s["id"] == ref or s.get("displayName", "").lower() == ref.lower():
            return s
    sys.exit("error: no printer share matching '%s'. Run: uprint printers" % ref)


def cmd_install(args):
    client, cfg = _client()
    share = _resolve_share(client, args.share)
    local_name = args.name or share.get("displayName", "Universal Printer")
    port = cfg.get("port", 8631)
    mapping = config.load_printers()
    mapping[local_name] = {"share_id": share["id"],
                           "share_name": share.get("displayName")}
    config.save_printers(mapping)
    try:
        cups.install_printer(local_name, port=port,
                             description="Universal Print: %s" % share.get("displayName"))
    except Exception as e:
        sys.exit("error: lpadmin failed: %s" % e)
    print()
    print("Done. '%s' now appears in System Settings -> Printers & Scanners" % local_name)
    print("and in the print dialog of every application.")
    print("Keep the IPP server running:  uprint serve   (or: uprint autostart)")


def cmd_uninstall(args):
    mapping = config.load_printers()
    if args.name not in mapping:
        sys.exit("error: '%s' is not a uprint-managed printer" % args.name)
    try:
        cups.uninstall_printer(args.name)
    except Exception as e:
        sys.exit("error: lpadmin failed: %s" % e)
    del mapping[args.name]
    config.save_printers(mapping)


def cmd_serve(args):
    cfg = config.load_config()
    port = args.port or cfg.get("port", 8631)
    server.serve(port=port)


def cmd_jobs(args):
    jobs = config.read_jobs(limit=args.limit)
    if not jobs:
        print("No jobs yet.")
        return
    for j in jobs:
        print("%(at)s  #%(job_id)s '%(name)s' -> %(status)s%(extra)s" % {
            "at": j.get("at", "?"), "job_id": j.get("job_id", "?"),
            "name": j.get("name", "?")[:40], "status": j.get("status", "?"),
            "extra": (" (%s)" % j["detail"][:60]) if j.get("detail") else "",
        })


def cmd_print(args):
    client, _cfg = _client()
    share = _resolve_share(client, args.share)
    if not os.path.exists(args.file):
        sys.exit("error: file not found: %s" % args.file)
    with open(args.file, "rb") as f:
        data = f.read()
    if not data.startswith(b"%PDF"):
        print("warning: file does not look like a PDF; Universal Print may reject it")
    name = os.path.basename(args.file)
    print("Uploading %s (%d bytes) to '%s'..."
          % (name, len(data), share.get("displayName")))
    job_id = client.submit_pdf(share["id"], data, display_name=name, file_name=name)
    print("Submitted as Universal Print job %s" % job_id)


def cmd_autostart(_args):
    python_exe = sys.executable
    script_path = os.path.abspath(sys.argv[0])
    cfg = config.load_config()
    cups.install_autostart(python_exe, script_path, port=cfg.get("port", 8631))


def cmd_logout(_args):
    auth.logout()


def build_parser():
    p = argparse.ArgumentParser(
        prog="uprint",
        description="Open-source Universal Print client for macOS. "
                    "Printers installed via 'uprint install' appear in System "
                    "Settings and every app's print dialog.")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("login", help="Sign in with Microsoft Entra ID (device code flow)")
    s.add_argument("--client-id", help="Entra app registration Application (client) ID")
    s.add_argument("--tenant", help="Tenant ID/domain (default: common)")
    s.set_defaults(func=cmd_login)

    s = sub.add_parser("printers", help="List Universal Print printer shares")
    s.set_defaults(func=cmd_printers)

    s = sub.add_parser("install", help="Install a printer into macOS (needs sudo once)")
    s.add_argument("--share", required=True, help="Share ID or display name (see: uprint printers)")
    s.add_argument("--name", help="Local printer name (default: share display name)")
    s.set_defaults(func=cmd_install)

    s = sub.add_parser("uninstall", help="Remove an installed printer")
    s.add_argument("--name", required=True, help="Local printer name")
    s.set_defaults(func=cmd_uninstall)

    s = sub.add_parser("serve", help="Run the local IPP server (keep running while printing)")
    s.add_argument("--port", type=int, help="Listen port (default: 8631)")
    s.set_defaults(func=cmd_serve)

    s = sub.add_parser("autostart", help="Run 'uprint serve' automatically at login")
    s.set_defaults(func=cmd_autostart)

    s = sub.add_parser("jobs", help="Show recent print job statuses")
    s.add_argument("--limit", type=int, default=20)
    s.set_defaults(func=cmd_jobs)

    s = sub.add_parser("print", help="Print a PDF directly via Universal Print cloud")
    s.add_argument("file", help="PDF file to print")
    s.add_argument("--share", required=True, help="Share ID or display name")
    s.set_defaults(func=cmd_print)

    s = sub.add_parser("logout", help="Clear the cached sign-in")
    s.set_defaults(func=cmd_logout)

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\nInterrupted.")
    except RuntimeError as e:
        sys.exit("error: %s" % e)


if __name__ == "__main__":
    main()
