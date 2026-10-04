"""
Local IPP/1.1 print server (stdlib only).

Listens on 127.0.0.1:<port>. macOS adds it with:
    lpadmin -p "<name>" -E -v ipp://127.0.0.1:<port>/printers/<name> -m everywhere
After that the printer shows up in System Settings -> Printers & Scanners
and in every application's print dialog, exactly like a natively installed
printer.

Printed documents arrive as PDF (the only format we advertise, so macOS
renders to PDF for us). Each job is spooled to disk and a background worker
thread forwards it to Universal Print via the Graph API.
"""

import os
import queue
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import auth, config, graph, ipp

JOB_QUEUE = queue.Queue()
_JOB_COUNTER = [0]
_JOB_LOCK = threading.Lock()


def _next_job_id():
    with _JOB_LOCK:
        _JOB_COUNTER[0] += 1
        return _JOB_COUNTER[0]


def printer_attributes(queue_name, port):
    uri = "ipp://127.0.0.1:%d/printers/%s" % (port, urllib.parse.quote(queue_name))
    T = ipp
    return [
        (T.TAG_NAME, "printer-name", queue_name),
        (T.TAG_URI, "printer-uri-supported", uri),
        (T.TAG_KEYWORD, "uri-security-supported", "none"),
        (T.TAG_KEYWORD, "uri-authentication-supported", "none"),
        (T.TAG_ENUM, "printer-state", 3),  # idle
        (T.TAG_KEYWORD, "printer-state-reasons", "none"),
        (T.TAG_BOOLEAN, "printer-is-accepting-jobs", True),
        (T.TAG_KEYWORD, "ipp-versions-supported", ["1.0", "1.1"]),
        (T.TAG_ENUM, "operations-supported", [
            ipp.OP_PRINT_JOB, ipp.OP_VALIDATE_JOB,
            ipp.OP_GET_PRINTER_ATTRIBUTES, ipp.OP_GET_JOBS,
            ipp.OP_GET_JOB_ATTRIBUTES, ipp.OP_CANCEL_JOB,
        ]),
        (T.TAG_MIMETYPE, "document-format-supported", "application/pdf"),
        (T.TAG_MIMETYPE, "document-format-default", "application/pdf"),
        (T.TAG_CHARSET, "charset-supported", "utf-8"),
        (T.TAG_BOOLEAN, "color-supported", True),
        (T.TAG_KEYWORD, "sides-supported", "one-sided"),
        (T.TAG_KEYWORD, "sides-default", "one-sided"),
        (T.TAG_KEYWORD, "print-quality-supported", ["draft", "normal", "high"]),
        (T.TAG_KEYWORD, "media-supported", ["iso_a4_210x297mm", "na_letter_8.5x11in"]),
        (T.TAG_KEYWORD, "media-default", "iso_a4_210x297mm"),
        (T.TAG_INTEGER, "queued-job-count", 0),
        (T.TAG_KEYWORD, "pdl-override-supported", "not-attempted"),
        (T.TAG_INTEGER, "printer-up-time", int(time.time())),
    ]


class IPPHandler(BaseHTTPRequestHandler):
    server_version = "uprint/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # quieter logs
        pass

    def _send_ipp(self, body):
        data = bytes(body)
        self.send_response(200)
        self.send_header("Content-Type", "application/ipp")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        try:
            _ver, op_id, req_id, groups, document = ipp.parse_request(raw)
        except ipp.IPPError as e:
            self._send_ipp(ipp.error_response(1, ipp.STATUS_BAD_REQUEST, str(e)))
            return
        queue_name = self._queue_name()
        op_name = ipp.OP_NAMES.get(op_id, hex(op_id))
        print("[ipp] %s %s" % (op_name, queue_name), flush=True)

        if op_id == ipp.OP_GET_PRINTER_ATTRIBUTES:
            cfg = config.load_config()
            attrs = printer_attributes(queue_name, cfg.get("port", 8631))
            self._send_ipp(ipp.ok_response(req_id, printer_attrs=attrs))
        elif op_id == ipp.OP_VALIDATE_JOB:
            self._send_ipp(ipp.ok_response(req_id))
        elif op_id == ipp.OP_PRINT_JOB:
            job_id = self._handle_print_job(queue_name, groups, document)
            job_attrs = [
                (ipp.TAG_INTEGER, "job-id", job_id),
                (ipp.TAG_URI, "job-uri",
                 "ipp://127.0.0.1/printers/%s/%d" % (queue_name, job_id)),
                (ipp.TAG_ENUM, "job-state", 3),  # pending
                (ipp.TAG_KEYWORD, "job-state-reasons", "none"),
            ]
            self._send_ipp(ipp.ok_response(req_id, job_attrs=job_attrs))
        elif op_id in (ipp.OP_GET_JOBS, ipp.OP_GET_JOB_ATTRIBUTES):
            self._send_ipp(ipp.ok_response(req_id))
        elif op_id == ipp.OP_CANCEL_JOB:
            self._send_ipp(ipp.ok_response(req_id))
        else:
            self._send_ipp(ipp.error_response(req_id, ipp.STATUS_BAD_REQUEST,
                                              "unsupported operation"))

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"uprint IPP server: POST application/ipp here\n")

    def _queue_name(self):
        # path: /printers/<name>
        parts = urllib.parse.unquote(self.path).strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "printers":
            return parts[1]
        return "default"

    def _handle_print_job(self, queue_name, groups, document):
        job_id = _next_job_id()
        job_name = ipp.get_attr(groups, "job-name", "Untitled") or "Untitled"
        if isinstance(job_name, bytes):
            job_name = job_name.decode("utf-8", "replace")
        spool_path = os.path.join(config.SPOOL_DIR, "job-%d.pdf" % job_id)
        with open(spool_path, "wb") as f:
            f.write(document)
        print("[spool] job %d '%s' (%d bytes) -> %s"
              % (job_id, job_name, len(document), spool_path), flush=True)
        JOB_QUEUE.put({
            "job_id": job_id, "queue": queue_name, "name": str(job_name),
            "path": spool_path, "size": len(document),
        })
        return job_id


def upload_worker(stop_event):
    """Background thread: forward spooled jobs to Universal Print."""
    while not stop_event.is_set():
        try:
            job = JOB_QUEUE.get(timeout=1)
        except queue.Empty:
            continue
        try:
            _forward_job(job)
        except Exception as e:  # never kill the worker on one bad job
            print("[error] job %d failed: %s" % (job["job_id"], e), flush=True)
            config.log_job({"job_id": job["job_id"], "queue": job["queue"],
                            "name": job["name"], "status": "failed",
                            "detail": str(e)[:200]})
        finally:
            JOB_QUEUE.task_done()


def _forward_job(job):
    cfg = config.load_config()
    printers = config.load_printers()
    mapping = printers.get(job["queue"])
    if not mapping:
        raise RuntimeError("no Universal Print share mapped to queue '%s' "
                           "(run: uprint install)" % job["queue"])
    share_id = mapping["share_id"]
    token = auth.get_access_token(tenant=cfg.get("tenant", "common"),
                                  client_id=cfg.get("client_id"))
    client = graph.GraphClient(token)
    with open(job["path"], "rb") as f:
        pdf = f.read()
    print("[cloud] uploading job %d '%s' to '%s' (%d bytes)..."
          % (job["job_id"], job["name"], mapping.get("share_name", share_id),
             len(pdf)), flush=True)
    cloud_id = client.submit_pdf(share_id, pdf, display_name=job["name"],
                                 file_name="job-%d.pdf" % job["job_id"])
    print("[cloud] job %d submitted as Universal Print job %s"
          % (job["job_id"], cloud_id), flush=True)
    config.log_job({"job_id": job["job_id"], "queue": job["queue"],
                    "name": job["name"], "status": "submitted",
                    "cloud_job_id": cloud_id, "share": mapping.get("share_name")})
    try:
        os.remove(job["path"])
    except OSError:
        pass


def serve(port=8631, foreground=True):
    config.ensure_dirs()
    server = ThreadingHTTPServer(("127.0.0.1", port), IPPHandler)
    stop_event = threading.Event()
    worker = threading.Thread(target=upload_worker, args=(stop_event,), daemon=True)
    worker.start()
    print("uprint IPP server listening on 127.0.0.1:%d" % port)
    print("Install a printer with:  uprint install --share <id> --name \"My Printer\"")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        server.server_close()
