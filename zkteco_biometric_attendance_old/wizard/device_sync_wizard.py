# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import UserError


class ZkDeviceSyncWizard(models.TransientModel):
    _name = "zk.device.sync.wizard"
    _description = "Manual ZK Device Sync"

    device_ids = fields.Many2many(
        "zk.device", string="Devices",
        domain=[("connection_mode", "in", ("pyzk", "hybrid")), ("active", "=", True)],
        required=True,
    )
    result_summary = fields.Text(readonly=True)

    def action_sync_now(self):
        self.ensure_one()
        if not self.device_ids:
            raise UserError(_("Select at least one device."))

        lines = []
        for device in self.device_ids:
            before = device.last_sync_count
            device.action_download_attendance()
            if device.last_error:
                lines.append(f"{device.name}: FAILED — {device.last_error}")
            else:
                lines.append(f"{device.name}: OK — {device.last_sync_count} record(s)")

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Sync Complete"),
                "message": "\n".join(lines),
                "sticky": True,
                "type": "info",
            },
        }
