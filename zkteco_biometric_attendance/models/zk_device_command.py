# -*- coding: utf-8 -*-
"""
Command queue for devices Odoo cannot dial directly (ADMS or Hybrid mode).

A PyZK device gets commands executed immediately over the open TCP
connection (see PyZKService.restart_device(), .clear_attendance(), etc.)
— there is nothing to queue. An ADMS-only device only ever calls OUT to
Odoo, so "reboot that device" has to be queued here and picked up the
next time the device polls GET /iclock/getrequest, per the ZKTeco PUSH
protocol's `C:<id>:<command>` convention.
"""
from odoo import fields, models


class ZkDeviceCommand(models.Model):
    _name = "zk.device.command"
    _description = "Queued ADMS Device Command"
    _order = "create_date desc"

    device_id = fields.Many2one("zk.device", required=True, ondelete="cascade", index=True)
    command_id = fields.Integer(
        string="Command #", required=True, copy=False,
        help="Per-device incrementing id. This is the <id> in the protocol's "
             "'C:<id>:<command>' line, and the device echoes it back in its "
             "ID=<id> result so we know which queued command it refers to.",
    )
    command_type = fields.Selection(
        [
            ("reboot", "Reboot"),
            ("clear_attendance", "Clear Attendance Log"),
            ("clear_data", "Clear All Data"),
            ("enable_device", "Enable Device"),
            ("disable_device", "Disable Device"),
            ("update_user", "Update User Info"),
            ("custom", "Custom"),
        ],
        required=True, default="custom",
    )
    command_text = fields.Char(
        required=True,
        help="Raw command string as sent to the device, e.g. 'REBOOT' or "
             "'DATA UPDATE USERINFO PIN=1001\\tName=Jane...'.",
    )
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("sent", "Sent"),
            ("done", "Done"),
            ("failed", "Failed"),
        ],
        default="pending", required=True, index=True,
    )
    result_code = fields.Char(readonly=True)
    result_text = fields.Text(readonly=True)
    sent_date = fields.Datetime(readonly=True)
    done_date = fields.Datetime(readonly=True)

    _sql_constraints = [
        (
            "device_command_id_uniq",
            "unique(device_id, command_id)",
            "Command id must be unique per device.",
        ),
    ]

    # Human-readable command strings for the common cases — kept here so
    # both the device model (queuing) and any future UI stay in sync with
    # the exact protocol syntax the device expects.
    COMMAND_TEXT = {
        "reboot": "REBOOT",
        "clear_attendance": "CLEAR LOG",
        "clear_data": "CLEAR DATA",
        "enable_device": "ENABLE DEVICE",
        "disable_device": "DISABLE DEVICE",
    }
