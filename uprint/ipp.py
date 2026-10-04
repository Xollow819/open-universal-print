"""
Minimal IPP/1.1 protocol encoder/decoder (RFC 8010 subset).

Only what a small print server needs: parse incoming requests and build
responses. No external dependencies.
"""

import struct

# --- Group tags ---
GROUP_OPERATION = 0x01
GROUP_JOB = 0x02
GROUP_END = 0x03
GROUP_PRINTER = 0x04

# --- Value tags ---
TAG_INTEGER = 0x21
TAG_BOOLEAN = 0x22
TAG_ENUM = 0x23
TAG_KEYWORD = 0x44
TAG_URI = 0x45
TAG_CHARSET = 0x47
TAG_LANGUAGE = 0x48
TAG_MIMETYPE = 0x49
TAG_NAME = 0x42
TAG_TEXT = 0x41

# --- Operations ---
OP_PRINT_JOB = 0x0002
OP_VALIDATE_JOB = 0x0004
OP_GET_JOB_ATTRIBUTES = 0x0008
OP_GET_JOBS = 0x0009
OP_GET_PRINTER_ATTRIBUTES = 0x000B
OP_CANCEL_JOB = 0x000C

# --- Status codes ---
STATUS_OK = 0x0000
STATUS_BAD_REQUEST = 0x0400
STATUS_NOT_FOUND = 0x0406

OP_NAMES = {
    OP_PRINT_JOB: "Print-Job",
    OP_VALIDATE_JOB: "Validate-Job",
    OP_GET_JOB_ATTRIBUTES: "Get-Job-Attributes",
    OP_GET_JOBS: "Get-Jobs",
    OP_GET_PRINTER_ATTRIBUTES: "Get-Printer-Attributes",
    OP_CANCEL_JOB: "Cancel-Job",
}


class IPPError(Exception):
    pass


def _pack_string(s):
    if isinstance(s, str):
        s = s.encode("utf-8")
    return struct.pack(">H", len(s)) + s


def encode_attribute(tag, name, values):
    """Encode one attribute (possibly multi-valued) to bytes."""
    if not isinstance(values, (list, tuple)):
        values = [values]
    out = b""
    first = True
    for v in values:
        if isinstance(v, bool):
            raw = b"\x01" if v else b"\x00"
        elif isinstance(v, int):
            raw = struct.pack(">i", v)
        elif isinstance(v, str):
            raw = v.encode("utf-8")
        elif isinstance(v, bytes):
            raw = v
        else:
            raise IPPError("unsupported attribute value type: %r" % type(v))
        name_part = _pack_string(name) if first else b"\x00\x00"
        out += struct.pack("B", tag) + name_part + _pack_string(raw)
        first = False
    return out


def encode_response(request_id, status_code, groups):
    """
    groups: list of (group_tag, [(value_tag, name, values), ...])
    Returns the full IPP response body.
    """
    out = struct.pack(">HHI", 0x0101, status_code, request_id)
    for group_tag, attrs in groups:
        out += struct.pack("B", group_tag)
        for tag, name, values in attrs:
            out += encode_attribute(tag, name, values)
    out += struct.pack("B", GROUP_END)
    return out


def ok_response(request_id, printer_attrs=(), job_attrs=()):
    op_group = [
        (TAG_CHARSET, "attributes-charset", "utf-8"),
        (TAG_LANGUAGE, "attributes-natural-language", "en"),
    ]
    groups = [(GROUP_OPERATION, op_group)]
    if printer_attrs:
        groups.append((GROUP_PRINTER, list(printer_attrs)))
    if job_attrs:
        groups.append((GROUP_JOB, list(job_attrs)))
    return encode_response(request_id, STATUS_OK, groups)


def error_response(request_id, status_code, message=""):
    op_group = [
        (TAG_CHARSET, "attributes-charset", "utf-8"),
        (TAG_LANGUAGE, "attributes-natural-language", "en"),
    ]
    if message:
        op_group.append((TAG_TEXT, "status-message", message))
    return encode_response(request_id, status_code, [(GROUP_OPERATION, op_group)])


def parse_request(data):
    """
    Parse an IPP request body.
    Returns (version, operation_id, request_id, groups, trailing_bytes)
    where groups is a list of (group_tag, [(value_tag, name, [values])]).
    trailing_bytes is the document data after end-of-attributes (may be b"").
    """
    if len(data) < 8:
        raise IPPError("request too short")
    version, op_id, request_id = struct.unpack(">HHI", data[:8])
    pos = 8
    groups = []
    current = None
    last_name = None
    last_tag = None
    while pos < len(data):
        tag = data[pos]
        pos += 1
        if tag == GROUP_END:
            trailing = data[pos:]
            return version, op_id, request_id, groups, trailing
        if tag in (GROUP_OPERATION, GROUP_JOB, GROUP_PRINTER):
            current = (tag, [])
            groups.append(current)
            last_name = None
            continue
        # value tag -> attribute
        if current is None:
            raise IPPError("attribute outside group")
        if pos + 2 > len(data):
            raise IPPError("truncated name length")
        name_len = struct.unpack(">H", data[pos:pos + 2])[0]
        pos += 2
        if name_len == 0:
            name, vtag = last_name, last_tag  # additional value
        else:
            if pos + name_len > len(data):
                raise IPPError("truncated name")
            name = data[pos:pos + name_len].decode("utf-8", "replace")
            pos += name_len
            vtag = tag
            last_name, last_tag = name, tag
        if pos + 2 > len(data):
            raise IPPError("truncated value length")
        val_len = struct.unpack(">H", data[pos:pos + 2])[0]
        pos += 2
        if pos + val_len > len(data):
            raise IPPError("truncated value")
        raw = data[pos:pos + val_len]
        pos += val_len
        value = _decode_value(vtag, raw)
        # merge into current group's attribute list
        attrs = current[1]
        for i, (t, n, vals) in enumerate(attrs):
            if n == name:
                vals.append(value)
                break
        else:
            attrs.append((vtag, name, [value]))
    raise IPPError("missing end-of-attributes tag")


def _decode_value(tag, raw):
    if tag in (TAG_INTEGER, TAG_ENUM):
        return struct.unpack(">i", raw)[0] if len(raw) == 4 else raw
    if tag == TAG_BOOLEAN:
        return raw == b"\x01"
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw


def get_attr(groups, name, default=None):
    for _gtag, attrs in groups:
        for _tag, aname, values in attrs:
            if aname == name:
                return values[0] if len(values) == 1 else values
    return default
