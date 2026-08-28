# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.addons.base.models.res_partner import _tz_get
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# How long (seconds) since the last ADMS heartbeat before we consider
# a cloud-push device "offline". Kept as a constant so it is easy to
# turn into a system parameter later without touching the model.
ADMS_OFFLINE_THRESHOLD = 180


class ZkDevice(models.Model):
    _name = "zk.device"
    _description = "ZK Biometric Device"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )

    serial_number = fields.Char(
        string="Serial Number", index=True, copy=False,
        help="Must match the SN the device reports (PyZK get_serialnumber() "
             "or the ADMS SN query-string parameter).",
    )

    tz = fields.Selection(
        _tz_get, string="Device Timezone",
        default=lambda self: self.env.company.partner_id.tz or "UTC",
        help="Wall-clock timezone the physical device is set to. Punch "
             "timestamps received from this device — via PyZK or ADMS — "
             "are naive local times and are interpreted in THIS timezone "
             "before being converted to UTC for storage. Get this wrong "
             "and every punch will be off by the UTC offset.",
    )

    connection_mode = fields.Selection(
        [
            ("pyzk", "PyZK (Direct TCP/IP)"),
            ("adms", "ADMS (Cloud Push)"),
            ("hybrid", "Hybrid (ADMS attendance + PyZK control)"),
        ],
        default="pyzk",
        required=True,
        tracking=True,
    )

    # ---- PyZK (direct) settings -------------------------------------------------
    device_ip = fields.Char(string="Device IP")
    device_port = fields.Integer(string="Device Port", default=4370)
    zk_password = fields.Integer(string="Comm Key", default=0,
                                  help="ZK 'commkey' password, 0 if not set on the device.")
    zk_timeout = fields.Float(string="Timeout (s)", default=5.0)
    zk_force_udp = fields.Boolean(string="Force UDP", default=False)
    zk_ommit_ping = fields.Boolean(string="Skip Ping Check", default=True)

    # ---- ADMS (cloud push) settings ---------------------------------------------
    adms_enabled = fields.Boolean(
        string="ADMS Enabled", compute="_compute_adms_enabled", store=True
    )
    adms_url = fields.Char(
        string="ADMS Push URL", compute="_compute_adms_url",
        help="Configure this exact URL on the device's Cloud/ADMS server settings.",
    )
    adms_last_heartbeat = fields.Datetime(string="Last ADMS Heartbeat")
    adms_push_version = fields.Char(string="Push Protocol Version")
    adms_firmware = fields.Char(string="Firmware Version")

    # ---- shared status ------------------------------------------------------------
    state = fields.Selection(
        [
            ("unknown", "Unknown"),
            ("online", "Online"),
            ("offline", "Offline"),
        ],
        default="unknown",
        compute="_compute_state",
        store=True,
    )
    last_connection = fields.Datetime(string="Last PyZK Connection")
    last_sync = fields.Datetime(string="Last Attendance Sync")
    last_sync_count = fields.Integer(string="Records In Last Sync", readonly=True)
    last_error = fields.Text(string="Last Error", readonly=True)

    user_mapping_ids = fields.One2many(
        "zk.user.mapping", "device_id", string="Device Users"
    )
    user_mapping_count = fields.Integer(compute="_compute_user_mapping_count")
    attendance_log_ids = fields.One2many(
        "zk.attendance.log", "device_id", string="Raw Logs"
    )
    attendance_log_count = fields.Integer(compute="_compute_attendance_log_count")
    command_ids = fields.One2many(
        "zk.device.command", "device_id", string="Queued Commands"
    )
    command_pending_count = fields.Integer(compute="_compute_command_pending_count")

    _sql_constraints = [
        (
            "serial_number_company_uniq",
            "unique(serial_number, company_id)",
            "A device with this serial number already exists in this company.",
        ),
    ]

    # ------------------------------------------------------------------ computes --
    @api.depends("connection_mode")
    def _compute_adms_enabled(self):
        for device in self:
            device.adms_enabled = device.connection_mode in ("adms", "hybrid")

    @api.depends("serial_number")
    def _compute_adms_url(self):
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url") or ""
        for device in self:
            device.adms_url = f"{base_url}"

    @api.depends("connection_mode", "adms_last_heartbeat", "last_connection")
    def _compute_state(self):
        now = fields.Datetime.now()
        for device in self:
            if device.connection_mode == "pyzk":
                device.state = "online" if device.last_connection and \
                    (now - device.last_connection) < timedelta(minutes=5) else \
                    ("unknown" if not device.last_connection else "offline")
            else:
                # adms or hybrid -> rely on heartbeat
                if not device.adms_last_heartbeat:
                    device.state = "unknown"
                elif (now - device.adms_last_heartbeat).total_seconds() <= ADMS_OFFLINE_THRESHOLD:
                    device.state = "online"
                else:
                    device.state = "offline"

    def _compute_user_mapping_count(self):
        grouped = self.env["zk.user.mapping"]._read_group(
            [("device_id", "in", self.ids)], ["device_id"], ["__count"]
        )
        counts = {device.id: count for device, count in grouped}
        for device in self:
            device.user_mapping_count = counts.get(device.id, 0)

    def _compute_attendance_log_count(self):
        grouped = self.env["zk.attendance.log"]._read_group(
            [("device_id", "in", self.ids)], ["device_id"], ["__count"]
        )
        counts = {device.id: count for device, count in grouped}
        for device in self:
            device.attendance_log_count = counts.get(device.id, 0)

    def _compute_command_pending_count(self):
        grouped = self.env["zk.device.command"]._read_group(
            [("device_id", "in", self.ids), ("state", "in", ("pending", "sent"))],
            ["device_id"], ["__count"],
        )
        counts = {device.id: count for device, count in grouped}
        for device in self:
            device.command_pending_count = counts.get(device.id, 0)

    # ------------------------------------------------------------------- actions --
    def action_test_connection(self):
        """PyZK: open a connection, read device info. ADMS: verify heartbeat."""
        self.ensure_one()
        if self.connection_mode == "adms":
            now = fields.Datetime.now()
            if not self.adms_last_heartbeat:
                raise UserError(_("No ADMS heartbeat received yet. Please check the device's Cloud Server Settings and ensure it is pointing to this Odoo server."))
            
            diff = (now - self.adms_last_heartbeat).total_seconds()
            if diff <= ADMS_OFFLINE_THRESHOLD:
                message = _("Device is Online! Last heartbeat received %d seconds ago.") % int(diff)
                msg_type = "success"
            else:
                message = _("Device is Offline. Last heartbeat was %d seconds ago (Threshold is %d).") % (int(diff), ADMS_OFFLINE_THRESHOLD)
                msg_type = "warning"
                
            self._compute_state()
            
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("ADMS Connection Status"),
                    "message": message,
                    "type": msg_type,
                },
            }
        from ..services.pyzk_service import PyZKService

        service = PyZKService(self)
        try:
            service.connect()
            info = service.get_device_info()
            self.write({
                "last_connection": fields.Datetime.now(),
                "last_error": False,
            })
            message = _("Connected OK. Serial: %(sn)s, Firmware: %(fw)s, Users: %(users)s") % {
                "sn": info.get("serial_number"),
                "fw": info.get("firmware_version"),
                "users": info.get("user_count"),
            }
            self.message_post(body=message)
        except Exception as exc:  # noqa: BLE001 - surfaced to the user deliberately
            self.write({"last_error": str(exc)})
            raise UserError(_("Connection failed: %s") % exc) from exc
        finally:
            service.disconnect()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Connection Successful"),
                "message": message,
                "type": "success",
            },
        }

    def action_download_attendance(self):
        """PyZK-only: pull raw punches from the device into zk.attendance.log,
        then hand them to the shared processor. Used by the button and by cron.
        """
        Log = self.env["zk.attendance.log"]
        Processor = self.env["zk.attendance.processor"]
        from ..services.pyzk_service import PyZKService

        for device in self:
            if device.connection_mode == "adms":
                continue
            service = PyZKService(device)
            try:
                service.connect()
                raw_records = service.get_attendance()
                created = Log._create_from_pyzk_records(device, raw_records)
                device.write({
                    "last_sync": fields.Datetime.now(),
                    "last_sync_count": len(created),
                    "last_connection": fields.Datetime.now(),
                    "last_error": False,
                })
                if created:
                    Processor.process_logs(created)
            except Exception as exc:  # noqa: BLE001
                _logger.exception("ZK sync failed for device %s", device.name)
                device.write({"last_error": str(exc)})
            finally:
                service.disconnect()
        return True

    def action_clear_device_attendance(self):
        """PyZK-only hardware action: wipe the punch log stored on the device
        itself, once Odoo has safely persisted it in zk.attendance.log.
        Deliberately requires manual confirmation from the user.
        """
        self.ensure_one()
        from ..services.pyzk_service import PyZKService

        service = PyZKService(self)
        try:
            service.connect()
            service.clear_attendance()
        finally:
            service.disconnect()
        self.message_post(body=_("On-device attendance log cleared by %s.") % self.env.user.name)
        return True

    def action_view_user_mappings(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "zk_attendance.action_zk_user_mapping"
        )
        action["domain"] = [("device_id", "=", self.id)]
        action["context"] = {"default_device_id": self.id}
        return action

    def action_view_attendance_logs(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "zk_attendance.action_zk_attendance_log"
        )
        action["domain"] = [("device_id", "=", self.id)]
        return action

    def action_view_commands(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "zk_attendance.action_zk_device_command"
        )
        action["domain"] = [("device_id", "=", self.id)]
        action["context"] = {"default_device_id": self.id}
        return action

    # ------------------------------------------------------ ADMS command queue --
    # For ADMS/Hybrid devices Odoo cannot dial out, so hardware actions are
    # queued here and picked up by the device's own GET /iclock/getrequest
    # poll (see controllers/adms_controller.py). A PyZK device never needs
    # this — action_clear_device_attendance() above executes immediately
    # over the open connection instead.
    def _next_command_id(self):
        self.ensure_one()
        last = self.env["zk.device.command"].search(
            [("device_id", "=", self.id)], order="command_id desc", limit=1
        )
        return (last.command_id or 0) + 1

    def _queue_command(self, command_type, command_text=None):
        self.ensure_one()
        if self.connection_mode == "pyzk":
            raise UserError(_(
                "%s is PyZK-only — hardware actions run immediately over the "
                "direct connection instead of being queued."
            ) % self.name)
        text = command_text or self.env["zk.device.command"].COMMAND_TEXT.get(command_type)
        if not text:
            raise UserError(_("No command text given for '%s'.") % command_type)
        return self.env["zk.device.command"].create({
            "device_id": self.id,
            "command_id": self._next_command_id(),
            "command_type": command_type,
            "command_text": text,
        })

    def action_queue_reboot(self):
        self.ensure_one()
        self._queue_command("reboot")
        self.message_post(body=_("Reboot queued — will run on the device's next check-in."))
        return True

    def action_queue_clear_attendance(self):
        self.ensure_one()
        self._queue_command("clear_attendance")
        self.message_post(body=_("Clear-attendance-log queued — will run on the device's next check-in."))
        return True

    def _dispatch_next_command(self):
        """Called by the ADMS controller on every GET /iclock/getrequest.
        Returns (command_id, command_text) for the oldest pending command,
        marking it 'sent', or None if the queue is empty."""
        self.ensure_one()
        command = self.env["zk.device.command"].search([
            ("device_id", "=", self.id), ("state", "=", "pending"),
        ], order="command_id asc", limit=1)
        if not command:
            return None
        command.write({"state": "sent", "sent_date": fields.Datetime.now()})
        return command.command_id, command.command_text

    def _apply_command_result(self, command_id, return_code, result_text=None):
        """Called by the ADMS controller on every POST /iclock/devicecmd."""
        self.ensure_one()
        command = self.env["zk.device.command"].search([
            ("device_id", "=", self.id), ("command_id", "=", command_id),
        ], limit=1)
        if not command:
            _logger.warning(
                "ADMS devicecmd result for unknown command #%s on device %s", command_id, self.name
            )
            return
        success = str(return_code) in ("0", "OK")
        command.write({
            "state": "done" if success else "failed",
            "result_code": str(return_code),
            "result_text": result_text or False,
            "done_date": fields.Datetime.now(),
        })

    # --------------------------------------------------------------------- cron --
    @api.model
    def cron_sync_devices(self):
        """Scheduled action: pull attendance from every PyZK / Hybrid device.
        ADMS-only devices are skipped — they push to us, we never dial them.
        """
        # Force recompute of all states so the UI correctly shows ADMS devices as offline after timeout
        self.search([])._compute_state()

        devices = self.search([
            ("active", "=", True),
            ("connection_mode", "in", ("pyzk", "hybrid")),
        ])
        for device in devices:
            try:
                device.action_download_attendance()
            except Exception:  # noqa: BLE001
                _logger.exception("Scheduled ZK sync failed for %s", device.name)
