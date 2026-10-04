"""
Thin Microsoft Graph client for Universal Print (v1.0), stdlib only.

Job submission flow (per Microsoft Learn):
  1. POST /print/shares/{shareId}/jobs            -> printJob + printDocument ids
  2. POST .../jobs/{jobId}/documents/{docId}/createUploadSession
                                                     -> uploadSession.uploadUrl
  3. PUT bytes to uploadUrl (Content-Range slices, 320 KiB multiples)
  4. POST .../jobs/{jobId}/start
"""

import json
import os
import urllib.error
import urllib.request

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
CHUNK_SIZE = 320 * 1024  # upload slices must be multiples of 320 KiB


class GraphError(Exception):
    pass


class GraphClient:
    def __init__(self, access_token):
        self.token = access_token

    # ---- low level -----------------------------------------------------
    def _request(self, method, path, body=None, extra_headers=None):
        url = path if path.startswith("http") else GRAPH_BASE + path
        data = None
        headers = {
            "Authorization": "Bearer " + self.token,
            "Accept": "application/json",
        }
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if extra_headers:
            headers.update(extra_headers)
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
                if not raw:
                    return None
                ctype = resp.headers.get("Content-Type", "")
                return json.loads(raw.decode("utf-8")) if "json" in ctype else raw
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            try:
                msg = json.loads(detail).get("error", {}).get("message", detail)
            except Exception:
                msg = detail
            raise GraphError("Graph %s %s -> HTTP %s: %s" % (method, path, e.code, msg))

    def get(self, path):
        return self._request("GET", path)

    def post(self, path, body=None):
        return self._request("POST", path, body)

    # ---- printer discovery ----------------------------------------------
    def list_shares(self):
        """Printer shares visible to the signed-in user."""
        out = []
        path = "/print/shares?$select=id,displayName,allowAllUsers&$top=100"
        while path:
            page = self.get(path)
            out.extend(page.get("value", []))
            nxt = page.get("@odata.nextLink")
            path = nxt[len(GRAPH_BASE):] if nxt and nxt.startswith(GRAPH_BASE) else None
        return out

    def get_printer_capabilities(self, share_id):
        """Content types etc. supported by the underlying printer."""
        try:
            printer = self.get("/print/shares/%s/printer?$select=capabilities" % share_id)
            caps = printer.get("capabilities") or {}
            return caps.get("contentTypes") or []
        except GraphError:
            return []

    # ---- job submission ---------------------------------------------------
    def create_job(self, share_id, display_name="uprint job", configuration=None):
        body = {"displayName": display_name}
        if configuration:
            body["configuration"] = configuration
        job = self.post("/print/shares/%s/jobs" % share_id, body)
        docs = job.get("documents") or []
        if not docs:
            raise GraphError("Graph returned a job without a document slot")
        return job["id"], docs[0]["id"]

    def create_upload_session(self, share_id, job_id, doc_id, file_name, size):
        body = {
            "properties": {
                "fileName": file_name,
                "contentType": "application/pdf",
                "size": size,
            }
        }
        session = self.post(
            "/print/shares/%s/jobs/%s/documents/%s/createUploadSession"
            % (share_id, job_id, doc_id),
            body,
        )
        url = session.get("uploadUrl")
        if not url:
            raise GraphError("No uploadUrl in upload session response")
        return url

    def upload_bytes(self, upload_url, data):
        """Upload a whole file, chunked per Graph upload-session rules."""
        size = len(data)
        offset = 0
        while offset < size:
            end = min(offset + CHUNK_SIZE, size) - 1
            chunk = data[offset:end + 1]
            headers = {
                "Content-Length": str(len(chunk)),
                "Content-Range": "bytes %d-%d/%d" % (offset, end, size),
            }
            req = urllib.request.Request(
                upload_url, data=chunk, headers=headers, method="PUT"
            )
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    resp.read()
            except urllib.error.HTTPError as e:
                raise GraphError("Upload failed at byte %d: HTTP %s" % (offset, e.code))
            offset = end + 1

    def start_job(self, share_id, job_id):
        return self.post("/print/shares/%s/jobs/%s/start" % (share_id, job_id), {})

    def get_job(self, share_id, job_id):
        return self.get(
            "/print/shares/%s/jobs/%s?$select=id,displayName,state,status" % (share_id, job_id)
        )

    def submit_pdf(self, share_id, pdf_bytes, display_name="uprint job", file_name="document.pdf"):
        """Full flow: create -> upload -> start. Returns (job_id, final_state)."""
        job_id, doc_id = self.create_job(share_id, display_name)
        url = self.create_upload_session(share_id, job_id, doc_id, file_name, len(pdf_bytes))
        self.upload_bytes(url, pdf_bytes)
        self.start_job(share_id, job_id)
        return job_id
