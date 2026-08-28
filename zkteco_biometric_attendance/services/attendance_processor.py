# -*- coding: utf-8 -*-
"""
The one place raw biometric punches (zk.attendance.log, written by EITHER
PyZK or ADMS) become real hr.attendance check-in/check-out records.

Registered as an Odoo model (not a plain class) purely so it can be reached
uniformly as `self.env["zk.attendance.processor"]` from the device model,
the ADMS controller, and the reprocess button — it holds no data of its own.
"""
import logging
from datetime import timedelta

from odoo import api, models

_logger = logging.getLogger(__name__)

# If the most recent open attendance (check_out=False) for an employee is
# older than this, we do NOT treat the next punch as its check-out — we
# assume the original check-out was missed and open a fresh attendance
# instead. This bounds how far "night shift rollover" is allowed to reach;
# tune per deployment (e.g. lower for office staff, higher for 24h shifts).
MAX_OPEN_ATTENDANCE_HOURS = 20


class ZkAttendanceProcessor(models.AbstractModel):
    _name = "zk.attendance.processor"
    _description = "ZK Raw Punch -> hr.attendance Processor"

    @api.model
    def process_logs(self, logs):
        """logs: zk.attendance.log recordset, any source, any device.
        Processes oldest-first per employee so open/close pairing is correct
        even if a batch arrives out of chronological order."""

        logs = logs.filtered(lambda log_rec: not log_rec.processed).sorted("punch_time")
        for log in logs:
            try:
                self._process_one(log)
            except Exception as exc:  # noqa: BLE001 - one bad punch must not block the batch
                _logger.exception("Failed to process zk.attendance.log %s", log.id)
                log.write({"processing_error": str(exc)})

    @api.model
    def _process_one(self, log):
        device_user_id = log.device_user_id

        if not device_user_id:
            log.write({
                "processing_error": (
                    f"Device user id '{log.device_user_id}' on device "
                    f"'{log.device_id.name}' is not mapped to an employee."
                ),
            })
            return

        # Find employee using zk.user.mapping
        employee = self.env["zk.user.mapping"]._find_employee(log.device_id, device_user_id)

        if not employee:
            log.write({
                "processing_error": (
                    f"No employee found mapped to user id "
                    f"'{device_user_id}' on this device."
                ),
            })
            return

        Attendance = self.env["hr.attendance"].sudo()

        # Find currently open attendance for this employee
        open_attendance = Attendance.search([
            ("employee_id", "=", employee.id),
            ("check_out", "=", False),
        ], order="check_in desc", limit=1)

        punch_dt = log.punch_time

        if open_attendance and self._is_valid_checkout(
            open_attendance, punch_dt
        ):
            if punch_dt <= open_attendance.check_in:
                log.write({
                    "processing_error": (
                        "Punch is earlier than the open check-in; "
                        "ignored as out-of-order."
                    ),
                })
                return

            open_attendance.write({
                "check_out": punch_dt,
                "zk_check_out_log_id": log.id,
            })

            self._finalize_attendance(open_attendance, log)

            log.write({
                "processed": True,
                "processing_error": False,
                "attendance_id": open_attendance.id,
            })
            return

        # Create new attendance
        new_attendance = Attendance.with_context(bypass_zk_attendance_validation=True).create({
            "employee_id": employee.id,
            "check_in": punch_dt,
            "zk_device_id": log.device_id.id,
            "zk_check_in_log_id": log.id,
            "zk_source": log.source,
        })

        self._finalize_attendance(new_attendance, log)

        log.write({
            "processed": True,
            "processing_error": False,
            "attendance_id": new_attendance.id,
        })
        
    @api.model
    def _is_valid_checkout(self, open_attendance, punch_dt):
        elapsed = punch_dt - open_attendance.check_in
        return timedelta(0) <= elapsed <= timedelta(hours=MAX_OPEN_ATTENDANCE_HOURS)

    @api.model
    def _finalize_attendance(self, attendance, log):
        """Extension hook — deliberately a no-op here. This is where
        client-specific rules (OT slab rounding, late-entry flagging,
        draft/confirmed/refused approval routing, missing-checkin records)
        should be added, by overriding this method in a thin follow-on
        module rather than editing this one."""
        return
