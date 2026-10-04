# open-universal-print

**uprint** — an open-source, terminal-native Universal Print client for macOS.
No App Store, no Apple Developer account, no system extensions, no entitlements.
Just Python, a terminal, and your Microsoft 365 tenant.

> Not affiliated with Microsoft. "Universal Print" is a trademark of Microsoft.

## What it does

Microsoft's official Universal Print Mac app installs a **system extension** to
make cloud printers appear in macOS. That installer is fragile (and requires
Apple's blessing). `uprint` takes a different, fully open route:

```
 ┌──────────────┐   IPP (localhost)   ┌──────────────────┐  Graph API   ┌────────────────┐
 │ Any Mac app  │ ─────────────────> │  uprint serve    │ ──────────> │ Universal Print│
 │ Print dialog │   PDF, driverless   │  (Python IPP     │  Entra ID    │ cloud (M365)   │
 └──────────────┘                    │   server)        │  device flow │                │
        ▲                            └──────────────────┘              └────────────────┘
        │                                    ▲ installed via lpadmin
 System Settings → Printers & Scanners ──────┘  (shows up like a native printer)
```

1. `uprint login` — sign in with Microsoft Entra ID (device-code flow, browser optional)
2. `uprint printers` — list your Universal Print printer shares
3. `uprint install` — creates a CUPS queue pointing at a localhost IPP server via `lpadmin`
4. The printer now appears in **System Settings → Printers & Scanners** and in every
   application's print dialog — exactly like Microsoft's app achieves, but with zero
   Apple-ecosystem gatekeeping.
5. `uprint serve` (or `uprint autostart`) runs the IPP server; printed PDFs are
   forwarded to the Universal Print cloud automatically.

## Prerequisites

- macOS 11+ with Python 3.9+ (`python3 --version`)
- A Microsoft 365 tenant with **Universal Print licenses** and at least one
  registered, shared printer (your IT admin handles this)
- An **app registration** in Microsoft Entra ID (see below) — you can create this
  yourself; one admin-consent click is needed

## One-time setup: Entra app registration

`uprint` talks to Microsoft Graph as *you* (delegated permissions). Register a
public client app once:

1. Go to **Entra admin center → Identity → Applications → App registrations → New registration**
   - Name: `uprint` (anything)
   - Supported account types: *Accounts in this organizational directory only*
   - Redirect URI: *Public client (mobile & desktop)* → `https://login.microsoftonline.com/common/oauth2/nativeclient`
2. **API permissions → Add a permission → Microsoft Graph → Delegated**:
   - `PrinterShare.ReadBasic.All` — list printer shares
   - `PrintJob.Create` — submit print jobs
   - `PrintJob.ReadBasic` — read job status
3. Click **Grant admin consent for \<your tenant\>** (an admin does this once).
4. Copy the **Application (client) ID** from the Overview page.

## Usage

```bash
# 0. Get the code (zero dependencies, stdlib only)
git clone https://github.com/<you>/open-universal-print.git
cd open-universal-print

# 1. Sign in (device code: visit the URL, enter the code)
python3 -m uprint login --client-id <APP_ID> [--tenant <TENANT_ID>]

# 2. See your printers
python3 -m uprint printers

# 3. Install one into macOS (asks for sudo once, for lpadmin)
python3 -m uprint install --share "<SHARE_ID_OR_NAME>" --name "Office Printer"

# 4. Run the print server (keep this terminal open while printing)
python3 -m uprint serve
#    ...or run it automatically at login:
python3 -m uprint autostart

# 5. Print from any app. Check what happened:
python3 -m uprint jobs

# Bonus: print a PDF straight to the cloud, no local install needed
python3 -m uprint print report.pdf --share "<SHARE_ID_OR_NAME>"

# Cleanup
python3 -m uprint uninstall --name "Office Printer"
python3 -m uprint logout
```

Config, token cache, spool and logs live in `~/.config/uprint/`.

## How it works (for the curious)

- **IPP server** (`uprint/server.py` + `uprint/ipp.py`): a minimal IPP/1.1
  implementation on `127.0.0.1:8631` using only the standard library. It answers
  `Get-Printer-Attributes` (advertising PDF-only, so macOS renders print jobs to
  PDF for us) and accepts `Print-Job`.
- **Install** (`uprint/cups.py`): `lpadmin -m everywhere` creates a driverless
  CUPS queue. CUPS queues always appear in Printers & Scanners — no driver,
  no system extension, no Apple approval involved.
- **Forwarding**: a background thread takes each spooled PDF and runs the
  documented Graph flow — create job → create upload session → PUT bytes
  (320 KiB chunks) → start job — against the mapped printer share.
- **Auth** (`uprint/auth.py`): OAuth2 device-code flow with refresh-token
  caching (`offline_access`), so you sign in once.

## Limitations (honest)

- PDF only. Universal Print accepts PDF universally; we deliberately advertise
  just `application/pdf` so macOS does the rendering.
- `uprint serve` must be running (foreground or via `autostart`) for installed
  printers to accept jobs.
- Installing via `lpadmin` needs admin (sudo) once per printer — normal macOS
  behavior, your own password, no Apple Developer anything.
- Tested on Linux for the IPP protocol/server path; the macOS `lpadmin` +
  print-dialog path needs a real Mac + tenant to verify end to end. Bug reports
  with logs (`~/.config/uprint/serve.log`, `jobs.log`) welcome.
- Your Entra admin must grant consent for the three Graph permissions once.

## License

MIT — see [LICENSE](LICENSE).
