# -*- coding: utf-8 -*-
import hashlib
import logging
from datetime import datetime

import pytz

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)

DEVICE_DT_FORMAT = "%Y-%m-%d %H:%M:%S"

# ZKTeco ATTLOG "status" byte -> punch type. Devices vary widely in how
# reliably they populate this, so it is stored for reference/reporting only
# — the attendance processor determines check-in vs check-out from each
# employee's open/closed attendance state, not from this field.
PUNCH_TYPE_SELECTION = [
    ("0", "Check In"),
    ("1", "Check Out"),
    ("2", "Break Out"),
    ("3", "Break In"),
    ("4", "Overtime In"),
    ("5", "Overtime Out"),
    ("255", "Unknown"),
]

VERIFY_TYPE_SELECTION = [
    ("0", "Password"),
    ("1", "Fingerprint"),
    ("2", "Card"),
    ("15", "Face"),
    ("255", "Unknown"),
]


class ZkAttendanceLog(models.Model):
    _name = "zk.attendance.log"
    _description = "Raw Biometric Attendance Punch"
    _order = "punch_time desc"
    _rec_name = "device_user_id"

    device_id = fields.Many2one("zk.device", required=True, index=True, ondelete="restrict")
    employee_id = fields.Many2one(
        "hr.employee", index=True,
        help="Resolved via zk.user.mapping at creation time. Empty means "
             "the device user id is not yet mapped to an employee.",
    )
    device_user_id = fields.Char(required=True, index=True)

    punch_time = fields.Datetime(required=True, index=True,
                                  help="Stored as UTC, per Odoo convention. The raw device/ADMS "
                                       "payload is naive local time and is converted using the "
                                       "originating device's own Timezone field (zk.device.tz) "
                                       "at creation time.")
    punch_type = fields.Selection(PUNCH_TYPE_SELECTION, default="255")
    verify_type = fields.Selection(VERIFY_TYPE_SELECTION, default="255")
    work_code = fields.Char()

    source = fields.Selection(
        [("pyzk", "PyZK"), ("adms", "ADMS"), ("manual", "Manual")],
        required=True, default="pyzk",
    )
    external_id = fields.Char(
        index=True, copy=False,
        help="SHA-256 fingerprint of device+user+timestamp+status, used to "
             "silently drop duplicates received from more than one transport "
             "(e.g. the same punch arriving via ADMS and again via a manual "
             "PyZK backfill).",
    )

    processed = fields.Boolean(default=False, index=True)
    processing_error = fields.Text()
    attendance_id = fields.Many2one(
        "hr.attendance", readonly=True, copy=False,
        help="The hr.attendance record this punch ultimately fed into.",
    )

    _sql_constraints = [
        (
            "external_id_uniq",
            "unique(external_id)",
            "Duplicate biometric punch (same device, user, timestamp and status).",
        ),
    ]

    @staticmethod
    def _make_fingerprint(device_id, device_user_id, punch_time, punch_type, verify_type):
        raw = f"{device_id}|{device_user_id}|{punch_time}|{punch_type}|{verify_type}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _device_local_to_utc_naive(device, punch_time):
        """punch_time: naive datetime OR 'YYYY-MM-DD HH:MM:SS' string, in
        the DEVICE's own wall-clock time (device.tz). Returns a naive
        datetime in UTC, ready to store in an Odoo Datetime field."""
        if isinstance(punch_time, str):
            naive_local = datetime.strptime(punch_time, DEVICE_DT_FORMAT)
        else:
            naive_local = punch_time
        device_tz = pytz.timezone(device.tz or "UTC")
        aware_local = device_tz.localize(naive_local)
        return aware_local.astimezone(pytz.UTC).replace(tzinfo=None)

    @api.model
    def _create_one(self, device, device_user_id, punch_time, punch_type, verify_type, work_code, source):
        """Shared entry point for both transports. `punch_time` must be the
        RAW device-local timestamp (naive datetime or string) — this method
        owns the local-to-UTC conversion, callers should not pre-convert it.
        Silently skips exact duplicates instead of raising, since a
        duplicate punch is an expected, routine occurrence, not an error."""
        punch_time_utc = self._device_local_to_utc_naive(device, punch_time)
        punch_type = str(punch_type) if punch_type is not None else "255"
        verify_type = str(verify_type) if verify_type is not None else "255"
        fingerprint = self._make_fingerprint(
            device.id, device_user_id, punch_time_utc, punch_type, verify_type
        )
        if self.search_count([("external_id", "=", fingerprint)]):
            return self.browse()

        employee = self.env["zk.user.mapping"]._find_employee(device, device_user_id)
        vals = {
            "device_id": device.id,
            "device_user_id": str(device_user_id),
            "employee_id": employee.id if employee else False,
            "punch_time": fields.Datetime.to_string(punch_time_utc),
            "punch_type": punch_type,
            "verify_type": verify_type,
            "work_code": work_code or False,
            "source": source,
            "external_id": fingerprint,
        }
        return self.create(vals)

    @api.model
    def _create_from_pyzk_records(self, device, raw_records):
        """raw_records: iterable of pyzk `Attendance` objects
        (attributes: user_id, timestamp, status, punch)."""
        created = self.browse()
        for record in raw_records:
            # record.timestamp is a naive datetime in the DEVICE's own local
            # clock (pyzk does not know or care about timezones) — pass it
            # straight through, _create_one() does the local -> UTC conversion.
            log = self._create_one(
                device=device,
                device_user_id=record.user_id,
                punch_time=record.timestamp,
                punch_type=getattr(record, "punch", None),
                verify_type=getattr(record, "status", None),
                work_code=None,
                source="pyzk",
            )
            if log:
                created |= log
        return created

    def action_reprocess(self):
        """Manual retry button for failed/unprocessed logs."""
        self.write({"processed": False, "processing_error": False})
        self.env["zk.attendance.processor"].process_logs(self)
        return True
