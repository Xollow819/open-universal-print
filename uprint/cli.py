"""uprint: driverless printing for macOS. No login, no drivers, no cloud."""

import argparse
import sys

from . import cups, discover


def cmd_discover(args):
    print("Scanning the local network for printers...\n")
    try:
        found = discover.discover(timeout=args.timeout)
    except RuntimeError as e:
        sys.exit("error: %s" % e)
    if not found:
        print("No printers found via Bonjour.")
        print("Tip: add one directly by IP:  uprint install --printer 192.168.1.10")
        return
    print("%-30s  %-12s  %s" % ("NAME", "TYPE", "DEVICE URI"))
    for name, stype, uri in found:
        print("%-30s  %-12s  %s" % (name[:30], stype, uri))
    print("\nInstall one with:  uprint install --printer \"<NAME>\" [--name \"My Printer\"]")


def cmd_install(args):
    uri = args.uri or discover.guess_uri(args.printer)
    local_name = args.name or args.printer
    try:
        cups.install_printer(local_name, uri,
                             description=args.description or "")
    except Exception as e:
        sys.exit("error: %s" % e)


def cmd_list(_args):
    printers = cups.list_printers()
    if not printers:
        print("No printers installed.")
        return
    default = cups.default_printer()
    for name, state in printers:
        mark = "  (default)" if name == default else ""
        print("%-28s  %s%s" % (name, state, mark))


def cmd_print(args):
    try:
        cups.print_file(args.printer, args.file)
    except Exception as e:
        sys.exit("error: %s" % e)


def cmd_remove(args):
    try:
        cups.remove_printer(args.printer)
    except Exception as e:
        sys.exit("error: %s" % e)


def build_parser():
    p = argparse.ArgumentParser(
        prog="uprint",
        description="Driverless printing for macOS. Discover printers on your "
                    "network, install them with zero drivers, and print — no "
                    "login, no accounts, no cloud.")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("discover", help="Find printers on the local network (Bonjour)")
    s.add_argument("--timeout", type=int, default=5, help="Scan seconds (default: 5)")
    s.set_defaults(func=cmd_discover)

    s = sub.add_parser("install", help="Install a printer, driverless (sudo needed once)")
    s.add_argument("--printer", required=True,
                   help="Printer name from discover, IP/hostname, or device URI")
    s.add_argument("--uri", help="Explicit device URI (overrides --printer guessing)")
    s.add_argument("--name", help="Local printer name (default: same as --printer)")
    s.add_argument("--description", default="", help="Description shown in Settings")
    s.set_defaults(func=cmd_install)

    s = sub.add_parser("list", help="Show installed printers")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("print", help="Print a file (PDF, images, text...)")
    s.add_argument("file", help="File to print")
    s.add_argument("--printer", help="Printer name (default: system default)")
    s.set_defaults(func=cmd_print)

    s = sub.add_parser("remove", help="Remove an installed printer (sudo needed once)")
    s.add_argument("--printer", required=True, help="Printer name")
    s.set_defaults(func=cmd_remove)

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
