"""
Microsoft Entra ID authentication using the OAuth2 device code flow.

Designed for terminal use: the user visits https://microsoft.com/devicelogin
on any device, enters a code, and this CLI polls until the token arrives.
Tokens are cached in ~/.config/uprint/tokens.json (mode 0600) with refresh
support via the offline_access scope, so login happens once.
"""

import json
import os
import time
import urllib.parse
import urllib.request

DEVICE_CODE_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/devicecode"
TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"

# Least-privilege delegated scopes for listing shares and submitting jobs.
DEFAULT_SCOPES = [
    "PrinterShare.ReadBasic.All",
    "PrintJob.Create",
    "PrintJob.ReadBasic",
    "offline_access",
]


def _config_dir():
    d = os.path.expanduser("~/.config/uprint")
    os.makedirs(d, mode=0o700, exist_ok=True)
    return d


def token_path():
    return os.path.join(_config_dir(), "tokens.json")


def _post_form(url, fields):
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def device_login(tenant="common", client_id=None, scopes=None):
    """Run the device code flow interactively. Returns the token response dict."""
    if not client_id:
        raise ValueError("client_id is required (register an app in Microsoft Entra ID)")
    scopes = scopes or DEFAULT_SCOPES
    scope_str = " ".join(scopes)

    dc = _post_form(
        DEVICE_CODE_URL.format(tenant=tenant),
        {"client_id": client_id, "scope": scope_str},
    )
    print()
    print("  To sign in, visit:  %s" % dc["verification_uri"])
    print("  And enter the code:  %s" % dc["user_code"])
    print()
    print("Waiting for you to sign in...", flush=True)

    interval = int(dc.get("interval", 5))
    expires_in = int(dc.get("expires_in", 900))
    deadline = time.time() + expires_in
    while time.time() < deadline:
        time.sleep(interval)
        try:
            token = _post_form(
                TOKEN_URL.format(tenant=tenant),
                {
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "client_id": client_id,
                    "device_code": dc["device_code"],
                },
            )
        except urllib.error.HTTPError as e:
            try:
                err = json.loads(e.read().decode("utf-8"))
                code = err.get("error")
            except Exception:
                raise
            if code == "authorization_pending":
                continue
            if code == "slow_down":
                interval += 5
                continue
            raise RuntimeError("Authentication failed: %s" % err.get("error_description", code))
        _save_token(token, tenant, client_id, scopes)
        print("Signed in successfully.")
        return token
    raise RuntimeError("Timed out waiting for sign-in.")


def _save_token(token, tenant, client_id, scopes):
    token["obtained_at"] = int(time.time())
    token["_tenant"] = tenant
    token["_client_id"] = client_id
    token["_scopes"] = scopes
    p = token_path()
    with open(p, "w") as f:
        json.dump(token, f)
    os.chmod(p, 0o600)


def load_token():
    p = token_path()
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return json.load(f)


def get_access_token(tenant="common", client_id=None, scopes=None):
    """Return a valid access token, refreshing silently when possible."""
    token = load_token()
    if not token:
        raise RuntimeError("Not signed in. Run: uprint login")
    expires_at = token.get("obtained_at", 0) + int(token.get("expires_in", 3600)) - 120
    if time.time() < expires_at:
        return token["access_token"]
    refresh = token.get("refresh_token")
    if not refresh:
        raise RuntimeError("Session expired. Run: uprint login")
    new = _post_form(
        TOKEN_URL.format(tenant=token.get("_tenant", tenant)),
        {
            "grant_type": "refresh_token",
            "client_id": token.get("_client_id", client_id),
            "refresh_token": refresh,
            "scope": " ".join(token.get("_scopes", scopes or DEFAULT_SCOPES)),
        },
    )
    _save_token(
        new,
        token.get("_tenant", tenant),
        token.get("_client_id", client_id),
        token.get("_scopes", scopes or DEFAULT_SCOPES),
    )
    return new["access_token"]


def logout():
    p = token_path()
    if os.path.exists(p):
        os.remove(p)
        print("Signed out (local token cache cleared).")
    else:
        print("Not signed in.")
