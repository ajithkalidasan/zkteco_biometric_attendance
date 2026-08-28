# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    zk_device_id = fields.Many2one("zk.device", readonly=True, copy=False,
                                    help="Device that produced the check-in punch.")
    zk_check_in_log_id = fields.Many2one("zk.attendance.log", readonly=True, copy=False)
    zk_check_out_log_id = fields.Many2one("zk.attendance.log", readonly=True, copy=False)
    zk_source = fields.Selection(
        [("pyzk", "PyZK"), ("adms", "ADMS"), ("manual", "Manual")],
        readonly=True, copy=False,
        help="Empty for attendance created through the normal kiosk/manual flow.",
    )
