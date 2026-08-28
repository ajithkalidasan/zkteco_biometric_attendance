# -*- coding: utf-8 -*-
"""
Helpers for the ZKTeco "PUSH SDK" (ADMS) protocol used by
controllers/adms_controller.py.

This is a text/line based protocol, NOT JSON — the device POSTs
tab-or-space separated rows to /iclock/cdata and expects short plain-text
acknowledgements back. Field layouts vary slightly by firmware, so parsing
here is deliberately tolerant (variable column count, tabs or runs of
whitespace) rather than a strict fixed-width parser.

Reference row shapes handled:

  ATTLOG (attendance):
      <pin>\\t<datetime>\\t<status>\\t<verify>\\t<workcode>\\t...

  OPERLOG (device operation / user-info log), only the USER lines are
  consumed here — enrollment/admin-log lines are stored raw but not acted on:
      USER PIN=<pin>\\tName=<name>\\tPri=<privilege>\\t...
"""
import logging

from odoo import fields

_logger = logging.getLogger(__name__)


def parse_attlog(body_text):
    """Yields dicts: {pin, datetime_str, status, verify, workcode}."""
    for line in body_text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        # Datetime is two space-separated tokens ("YYYY-MM-DD" "HH:MM:SS"),
        # everything else is single tokens, so rejoin defensively.
        if len(parts) < 4:
            _logger.warning("ADMS ATTLOG: skipping malformed line: %r", line)
            continue
        pin = parts[0]
        datetime_str = f"{parts[1]} {parts[2]}"
        status = parts[3] if len(parts) > 3 else "255"
        verify = parts[4] if len(parts) > 4 else "255"
        workcode = parts[5] if len(parts) > 5 else None
        yield {
            "pin": pin,
            "datetime_str": datetime_str,
            "status": status,
            "verify": verify,
            "workcode": workcode,
        }


def parse_operlog_user_lines(body_text):
    """Yields dicts for USER enrollment lines only; other OPERLOG rows
    (admin ops, fingerprint templates, face templates) are ignored here."""
    for line in body_text.splitlines():
        line = line.strip()
        if not line.startswith("USER"):
            continue
        fields_map = {}
        for token in line.split("\t")[1:]:
            if "=" in token:
                key, _, value = token.partition("=")
                fields_map[key.strip()] = value.strip()
        if fields_map.get("PIN"):
            yield fields_map


def build_registry_response(device):
    """Response to GET /iclock/registry — tells the device its polling
    parameters. Kept conservative (poll every 30s, realtime push on)."""
    sn = device.serial_number or ""
    lines = [
        f"GET OPTION FROM: {sn}",
        "Stamp=9999",
        "OpStamp=9999",
        "ATTLOGStamp=9999",
        "ErrorDelay=30",
        "Delay=30",
        "TransFlag=1111000000",
        "Realtime=1",
        "Encrypt=0",
    ]
    return "\n".join(lines) + "\n"


def build_cdata_ack(record_count):
    """Response to POST /iclock/cdata — the device expects this exact
    'OK: N' shape or it will keep resending the same batch."""
    return f"OK: {record_count}"


def build_getrequest_response(command_id, command_text):
    """Response to GET /iclock/getrequest when a command is queued.
    Protocol shape: 'C:<id>:<command>'."""
    return f"C:{command_id}:{command_text}\n"


def parse_devicecmd_result(body_text):
    """POST /iclock/devicecmd body: one result per line, fields separated
    by '&' as key=value pairs, e.g.:
        ID=1&Return=0&CMD=REBOOT
        ID=2&Return=-1&CMD=CLEAR LOG
    Yields dicts: {id, return_code, cmd}."""
    for line in body_text.splitlines():
        line = line.strip()
        if not line:
            continue
        fields_map = {}
        for token in line.split("&"):
            if "=" in token:
                key, _, value = token.partition("=")
                fields_map[key.strip().upper()] = value.strip()
        if "ID" not in fields_map:
            _logger.warning("ADMS devicecmd: skipping line with no ID: %r", line)
            continue
        try:
            command_id = int(fields_map["ID"])
        except ValueError:
            _logger.warning("ADMS devicecmd: non-numeric ID, skipping: %r", line)
            continue
        yield {
            "id": command_id,
            "return_code": fields_map.get("RETURN", "0"),
            "cmd": fields_map.get("CMD"),
        }
