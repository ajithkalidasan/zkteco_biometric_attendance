# -*- coding: utf-8 -*-
"""
ZKTeco "PUSH SDK" (ADMS) endpoints.

These routes are `auth="public"` by necessity — the device has no Odoo
session, only a URL configured in its own Cloud/ADMS settings. Every route
therefore re-validates the device by serial number before touching any
data; an unknown SN is rejected unless auto-registration is explicitly
turned on (ir.config_parameter `zk_attendance.adms_auto_register`).

All plain-text (not JSON) — this is what the firmware expects.
"""
import logging

from odoo import http, fields
from odoo.http import request

from ..services import adms_service

_logger = logging.getLogger(__name__)

PLAIN_TEXT_HEADERS = [("Content-Type", "text/plain")]


class ZkAdmsController(http.Controller):

    # ---------------------------------------------------------------- helpers --
    def _get_or_register_device(self, sn):
        Device = request.env["zk.device"].sudo()
        device = Device.search([("serial_number", "=", sn)], limit=1)
        if device:
            return device

        auto_register = request.env["ir.config_parameter"].sudo().get_param(
            "zk_attendance.adms_auto_register", "False"
        ) == "True"
        if not auto_register:
            _logger.warning("ADMS request from unregistered SN=%s rejected (auto-register off).", sn)
            return Device.browse()

        company = request.env["res.company"].sudo().search([], limit=1)
        device = Device.create({
            "name": f"ADMS-{sn}",
            "serial_number": sn,
            "connection_mode": "adms",
            "company_id": company.id,
        })
        _logger.info("Auto-registered new ADMS device SN=%s as %s", sn, device.id)
        return device

    def _touch_heartbeat(self, device, push_version=None):
        vals = {"adms_last_heartbeat": fields.Datetime.now()}
        if push_version:
            vals["adms_push_version"] = push_version
        device.sudo().write(vals)

    # ----------------------------------------------------------------- cdata --
    @http.route(["/iclock/cdata", "/iclock/cdata.aspx"], type="http", auth="public", methods=["GET"], csrf=False)
    def cdata_handshake(self, **kwargs):
        """Device calls this GET first, on power-up / heartbeat interval,
        e.g. /iclock/cdata?SN=xxx&options=all&pushver=2.4.1"""
        sn = kwargs.get("SN") or kwargs.get("sn")
        if not sn:
            return request.make_response("ERROR: SN required", headers=PLAIN_TEXT_HEADERS)

        device = self._get_or_register_device(sn)
        if not device:
            return request.make_response("ERROR: Unregistered device", headers=PLAIN_TEXT_HEADERS)

        self._touch_heartbeat(device, push_version=kwargs.get("pushver"))
        body = adms_service.build_registry_response(device)
        return request.make_response(body, headers=PLAIN_TEXT_HEADERS)

    @http.route(["/iclock/cdata", "/iclock/cdata.aspx"], type="http", auth="public", methods=["POST"], csrf=False)
    def cdata_upload(self, **kwargs):
        """Device POSTs punch/user data here, e.g.
        /iclock/cdata?SN=xxx&table=ATTLOG&Stamp=9999"""
        sn = kwargs.get("SN") or kwargs.get("sn")
        table = (kwargs.get("table") or "").upper()

        device = self._get_or_register_device(sn) if sn else None
        if not device:
            return request.make_response("ERROR: Unregistered device", headers=PLAIN_TEXT_HEADERS)

        self._touch_heartbeat(device)

        body_text = request.httprequest.get_data(as_text=True) or ""
        Log = request.env["zk.attendance.log"].sudo()
        Processor = request.env["zk.attendance.processor"].sudo()

        if table == "ATTLOG":
            rows = list(adms_service.parse_attlog(body_text))
            created = Log.browse()
            for row in rows:
                try:
                    log = Log._create_one(
                        device=device,
                        device_user_id=row["pin"],
                        punch_time=row["datetime_str"],
                        punch_type=row["status"],
                        verify_type=row["verify"],
                        work_code=row["workcode"],
                        source="adms",
                    )
                    if log:
                        created |= log
                except Exception:  # noqa: BLE001 - one bad row must not drop the whole batch/ack
                    _logger.exception("ADMS ATTLOG row failed to store: %r", row)
            if created:
                Processor.process_logs(created)
            device.write({"last_sync": fields.Datetime.now(), "last_sync_count": len(rows)})
            return request.make_response(adms_service.build_cdata_ack(len(rows)), headers=PLAIN_TEXT_HEADERS)

        if table == "OPERLOG":
            Mapping = request.env["zk.user.mapping"].sudo()
            rows = list(adms_service.parse_operlog_user_lines(body_text))
            for row in rows:
                mapping = Mapping.search([
                    ("device_id", "=", device.id),
                    ("device_user_id", "=", row.get("PIN")),
                ], limit=1)
                if mapping and row.get("Name"):
                    mapping.write({"device_user_name": row["Name"]})
            return request.make_response(adms_service.build_cdata_ack(len(rows)), headers=PLAIN_TEXT_HEADERS)

        # Unrecognized table (options upload, fp templates, etc.) — accept
        # and ignore rather than making the device retry forever.
        return request.make_response("OK", headers=PLAIN_TEXT_HEADERS)

    # -------------------------------------------------------------- registry --
    @http.route(["/iclock/registry", "/iclock/registry.aspx"], type="http", auth="public", methods=["GET", "POST"], csrf=False)
    def registry(self, **kwargs):
        sn = kwargs.get("SN") or kwargs.get("sn")
        if not sn:
            return request.make_response("ERROR: SN required", headers=PLAIN_TEXT_HEADERS)
        device = self._get_or_register_device(sn)
        if not device:
            return request.make_response("ERROR: Unregistered device", headers=PLAIN_TEXT_HEADERS)
        self._touch_heartbeat(device)
        return request.make_response(adms_service.build_registry_response(device), headers=PLAIN_TEXT_HEADERS)

    # ------------------------------------------------------------ getrequest --
    @http.route(["/iclock/getrequest", "/iclock/getrequest.aspx"], type="http", auth="public", methods=["GET"], csrf=False)
    def getrequest(self, **kwargs):
        """Device polls this periodically for queued commands (reboot,
        clear-log, etc — see zk.device._queue_command()). Dispatches the
        oldest pending zk.device.command, if any, and marks it 'sent'."""
        sn = kwargs.get("SN") or kwargs.get("sn")
        device = self._get_or_register_device(sn) if sn else None
        if not device:
            return request.make_response("ERROR: Unregistered device", headers=PLAIN_TEXT_HEADERS)

        self._touch_heartbeat(device)
        dispatched = device.sudo()._dispatch_next_command()
        if dispatched:
            command_id, command_text = dispatched
            body = adms_service.build_getrequest_response(command_id, command_text)
            return request.make_response(body, headers=PLAIN_TEXT_HEADERS)
        return request.make_response("OK", headers=PLAIN_TEXT_HEADERS)

    # ------------------------------------------------------------- devicecmd --
    @http.route(["/iclock/devicecmd", "/iclock/devicecmd.aspx"], type="http", auth="public", methods=["POST"], csrf=False)
    def devicecmd(self, **kwargs):
        """Device POSTs the result of a previously queued command here,
        e.g. 'ID=1&Return=0&CMD=REBOOT'. Matched back to zk.device.command
        by (device, command_id) and marked done/failed accordingly."""
        sn = kwargs.get("SN") or kwargs.get("sn")
        device = self._get_or_register_device(sn) if sn else None
        body_text = request.httprequest.get_data(as_text=True) or ""

        if device:
            for result in adms_service.parse_devicecmd_result(body_text):
                device.sudo()._apply_command_result(
                    result["id"], result["return_code"], result_text=result.get("cmd")
                )
        else:
            _logger.warning("ADMS devicecmd result from unregistered SN=%s: %s", sn, body_text[:500])

        return request.make_response("OK", headers=PLAIN_TEXT_HEADERS)
