# open-universal-print

**uprint** — driverless printing for macOS, from the terminal.
No login. No accounts. No cloud. No printer drivers. No App Store.

Your Mac already knows how to print to any AirPrint / IPP network printer
with zero drivers — `uprint` just makes it a one-liner.

## What it does

```
$ uprint discover
Scanning the local network for printers...

NAME                            TYPE          DEVICE URI
Office LaserJet                 _ipp._tcp     dnssd://Office%20LaserJet._ipp._tcp.local
Library Printer                 _ipp._tcp     dnssd://Library%20Printer._ipp._tcp.local

$ uprint install --printer "Office LaserJet"
[asks for sudo once]
Printer 'Office LaserJet' installed.

$ uprint print thesis.pdf --printer "Office LaserJet"
Sent to Office LaserJet.
```

Installed printers appear in **System Settings → Printers & Scanners** and in
every application's print dialog — exactly like a natively installed printer,
because that's what they are: plain CUPS queues using driverless
IPP Everywhere (`lpadmin -m everywhere`).

## Requirements

- macOS 11+ with Python 3.9+ (`python3 --version`)
- A printer on your local network (Wi-Fi/Ethernet), **or** its IP address
- Admin (sudo) once per printer install — your own password, nothing else

That's it. No Microsoft account, no Entra ID, no API keys, no sign-in.

## Usage

```bash
git clone https://github.com/<you>/open-universal-print.git
cd open-universal-print

# Find printers on the network (Bonjour)
python3 -m uprint discover

# Install one — by discovered name, IP/hostname, or full device URI
python3 -m uprint install --printer "Office LaserJet"
python3 -m uprint install --printer 192.168.1.10 --name "Lab Printer"
python3 -m uprint install --printer 192.168.1.10 --uri "ipp://192.168.1.10/ipp/print"

# Print anything (PDF, images, text...)
python3 -m uprint print document.pdf --printer "Office LaserJet"

# Manage
python3 -m uprint list
python3 -m uprint remove --printer "Office LaserJet"
```

Tip: make a shortcut so you don't type `python3 -m` every time:

```bash
echo 'alias uprint="python3 /path/to/open-universal-print -m uprint"' >> ~/.zshrc
```

## How it works

- **discover** — asks macOS's built-in `dns-sd` to browse Bonjour for
  `_ipp._tcp`, `_ipps._tcp` and `_printer._tcp` services. Whatever responds is
  a printer your Mac can already talk to.
- **install** — `lpadmin -p <name> -E -v <uri> -m everywhere`. The `everywhere`
  model means "this printer speaks driverless IPP" — macOS renders the job
  itself and no PPD or vendor driver is ever downloaded.
- **print** — hands the file to the system spooler (`lp`). PDF, PNG, JPEG and
  text all work out of the box.

## Limitations (honest)

- Only printers your Mac can reach: local network (Bonjour/IP) printers.
  Cloud print services (Universal Print, Google Cloud Print, vendor clouds)
  need their own accounts by design — this tool deliberately doesn't do that.
- `discover` needs Bonjour enabled on the network; some campus/enterprise
  Wi-Fi networks block mDNS — use `--printer <IP>` directly in that case.
- Installing/removing printers needs admin (sudo) once — standard macOS
  behavior.
- `dns-sd`/`lpadmin` behavior verified from docs and parser tests; the live
  Bonjour + print-dialog path needs a real Mac with a real printer to confirm
  end to end. Bug reports welcome.

## License

MIT — see [LICENSE](LICENSE). Not affiliated with Microsoft or Apple.
"Universal Print" is a trademark of Microsoft; this project is an independent
driverless-printing toolkit.
