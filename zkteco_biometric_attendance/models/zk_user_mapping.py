# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ZkUserMapping(models.Model):
    _name = "zk.user.mapping"
    _description = "ZK Device User -> Employee Mapping"
    _rec_name = "display_name"

    device_id = fields.Many2one("zk.device", required=True, ondelete="cascade", index=True)
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade", index=True)
    device_user_id = fields.Char(
        string="Device User ID", required=True, index=True,
        help="The numeric/alphanumeric user id as stored on the biometric device "
             "(this is NOT the Odoo employee id — one employee can have a "
             "different device_user_id on every device).",
    )
    device_user_name = fields.Char(
        string="Name On Device",
        help="Optional cache of the name as enrolled on the device, useful for "
             "spotting mismatches during onboarding.",
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(related="device_id.company_id", store=True)
    display_name = fields.Char(compute="_compute_display_name")

    _sql_constraints = [
        (
            "device_user_uniq",
            "unique(device_id, device_user_id)",
            "This device user id is already mapped to an employee on this device.",
        ),
    ]

    @api.depends("device_id.name", "employee_id.name", "device_user_id")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.employee_id.name or '?'} @ {rec.device_id.name or '?'} (#{rec.device_user_id or '?'})"

    @api.constrains("employee_id", "device_id")
    def _check_one_mapping_per_device(self):
        for rec in self:
            duplicate = self.search([
                ("id", "!=", rec.id),
                ("device_id", "=", rec.device_id.id),
                ("employee_id", "=", rec.employee_id.id),
            ], limit=1)
            if duplicate:
                raise ValidationError(_(
                    "%(employee)s is already mapped on device %(device)s (user id %(uid)s)."
                ) % {
                    "employee": rec.employee_id.name,
                    "device": rec.device_id.name,
                    "uid": duplicate.device_user_id,
                })

    @api.model
    def _find_employee(self, device, device_user_id):
        """Resolve an employee from a (device, device_user_id) pair.
        Returns an empty recordset if unmapped."""
        mapping = self.search([
            ("device_id", "=", device.id),
            ("device_user_id", "=", str(device_user_id)),
            ("active", "=", True),
        ], limit=1)
        return mapping.employee_id
