# -*- coding: utf-8 -*-
# attendance_processor.py is an Odoo model and must be imported here so the
# registry picks it up. pyzk_service.py and adms_service.py are plain helper
# classes (not models) and are imported directly where used, not via this
# package __init__ — pyzk_service in particular imports the third-party `zk`
# library lazily inside its own __init__, not at module level, so a
# missing/broken pyzk install never blocks module load on ADMS-only sites.
from . import attendance_processor
