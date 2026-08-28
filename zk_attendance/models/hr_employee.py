# -*- coding: utf-8 -*-
import pytz

from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    zk_user_mapping_ids = fields.One2many(
        "zk.user.mapping", "employee_id", string="Biometric Device IDs"
    )
    zk_user_mapping_count = fields.Integer(compute="_compute_zk_user_mapping_count")

    def _compute_zk_user_mapping_count(self):
        grouped = self.env["zk.user.mapping"]._read_group(
            [("employee_id", "in", self.ids)], ["employee_id"], ["__count"]
        )
        counts = {employee.id: count for employee, count in grouped}
        for employee in self:
            employee.zk_user_mapping_count = counts.get(employee.id, 0)

    def action_view_zk_mappings(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "zk_attendance.action_zk_user_mapping"
        )
        action["domain"] = [("employee_id", "=", self.id)]
        action["context"] = {"default_employee_id": self.id}
        return action

    def _attendance_tz(self):
        self.ensure_one()
        calendar = self.resource_calendar_id
        tz_name = (calendar.tz if calendar else False) or self.tz or "UTC"
        try:
            return pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            return pytz.UTC

    def _attendance_localize(self, dt_utc_naive):
        """dt_utc_naive: naive datetime already in UTC (Odoo's storage tz).
        Returns a tz-aware datetime in the employee's scheduled calendar tz."""
        self.ensure_one()
        if not dt_utc_naive:
            return dt_utc_naive
        aware_utc = pytz.UTC.localize(dt_utc_naive)
        return aware_utc.astimezone(self._attendance_tz())

    def _attendance_local_date(self, dt_utc_naive):
        """The calendar-day bucket a punch belongs to, in local time —
        used so a 1am overnight-shift check-out doesn't get filed under
        the wrong day."""
        localized = self._attendance_localize(dt_utc_naive)
        return localized.date() if localized else False
