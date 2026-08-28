# -*- coding: utf-8 -*-
from odoo import fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    adms_auto_register = fields.Boolean(
        string="ADMS Auto Register",
        config_parameter="zk_attendance.adms_auto_register",
        help="Automatically register unknown devices when they connect via ADMS for the first time."
    )
