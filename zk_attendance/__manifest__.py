# -*- coding: utf-8 -*-
{
    "name": "ZK Attendance",
    "summary": "Unified ZKTeco biometric attendance: PyZK (direct) and ADMS (cloud push) modes",
    "description": """
ZK Attendance
=============
Single Odoo module for ZKTeco biometric devices supporting three transport modes:

* **PyZK**   – Odoo connects directly to the device over TCP/IP (port 4370).
* **ADMS**   – the device pushes attendance to Odoo over HTTP (/iclock/*).
* **Hybrid** – ADMS is used for attendance, PyZK is used for device control.

Both transports write into a common `zk.attendance.log` raw table which is
then converted into `hr.attendance` records by a single, shared
`zk.attendance.processor` service.
""",
    "version": "19.0.1.0.0",
    "category": "Human Resources/Attendances",
    "author": "Ajith",
    "website": "https://www.smruthitechnologies.com",
    "license": "LGPL-3",
    "depends": ["hr_attendance", "hr", "mail"],
    "external_dependencies": {
        "python": ["zk"],
    },
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/zk_device_views.xml",
        "views/zk_device_command_views.xml",
        "views/zk_attendance_log_views.xml",
        "views/zk_user_mapping_views.xml",
        "views/hr_employee_views.xml",
        "wizard/device_sync_wizard_views.xml",
        "views/res_config_settings_views.xml",
        "views/hr_attendance_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}
