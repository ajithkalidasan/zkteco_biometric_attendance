from odoo import models, api, fields
from datetime import datetime, date
import calendar

class ZkAttendanceDashboard(models.AbstractModel):
    _name = "zk.attendance.dashboard"
    _description = "ZK Attendance Dashboard Data Provider"

    @api.model
    def get_dashboard_data(self):
        Device = self.env["zk.device"]
        Log = self.env["zk.attendance.log"]
        
        devices = Device.search([])
        today_str = date.today().strftime('%Y-%m-%d')
        
        today_logs = Log.search([('punch_time', '>=', today_str)])
        unprocessed_logs = Log.search([('processed', '=', False)])
        error_logs = Log.search([('processing_error', '!=', False)])
        recent_logs = Log.search([], order='punch_time desc', limit=10)
        
        device_data = []
        online_count = 0
        offline_count = 0
        for d in devices:
            state = "online" if d.connection_mode == "pyzk" else "offline"
            if state == "online":
                online_count += 1
            else:
                offline_count += 1
                
            device_data.append({
                'id': d.id,
                'name': d.name,
                'serial_number': d.serial_number or '',
                'state': state
            })
            
        recent_logs_data = []
        for l in recent_logs:
            recent_logs_data.append({
                'id': l.id,
                'punch_time': l.punch_time.strftime('%Y-%m-%d %H:%M:%S') if l.punch_time else '',
                'employee_name': l.employee_id.name if l.employee_id else '',
                'device_user_id': l.device_user_id or '',
                'device_name': l.device_id.name if l.device_id else '',
                'processing_error': l.processing_error
            })
            
        return {
            'device_count': len(devices),
            'online_device_count': online_count,
            'offline_device_count': offline_count,
            'log_count': Log.search_count([]),
            'today_log_count': len(today_logs),
            'unprocessed_log_count': len(unprocessed_logs),
            'error_log_count': len(error_logs),
            'last_punch_time': recent_logs[0].punch_time.strftime('%Y-%m-%d %H:%M:%S') if recent_logs else "",
            'devices': device_data,
            'recent_logs': recent_logs_data,
        }
