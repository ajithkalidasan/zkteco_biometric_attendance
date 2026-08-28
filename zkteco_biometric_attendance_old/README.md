# ZK Attendance

A unified, robust ZKTeco biometric attendance integration module for **Odoo 19 Community/Enterprise**. 

Unlike other modules that force you into a single connection method, this module supports three transport modes out of the box:
* **PyZK** – Odoo connects directly to the device over TCP/IP (typically port 4370). Perfect for local networks.
* **ADMS (Cloud Push)** – The device pushes attendance logs to Odoo over HTTP (`/iclock/cdata`). Ideal for remote sites without static IPs or VPNs.
* **Hybrid** – Uses ADMS for real-time attendance pushes, while keeping PyZK available for executing immediate device commands (like rebooting or clearing logs).

Regardless of the transport method, all punches funnel through a single, shared `zk.attendance.log` raw table and are processed by a unified `zk.attendance.processor`. This ensures that check-in/check-out logic, deduplication, employee mapping, and timezone handling are consistently applied across all devices.

---

## Key Features

- **Multi-Transport Support**: Easily mix and match PyZK and ADMS devices across your organization.
- **Deduplication**: Uses SHA-256 fingerprinting on raw logs to silently ignore duplicate punches (even if received from different transports, like an ADMS push followed by a PyZK manual sync).
- **Flexible User Mapping**: Map employees to biometric user IDs on a *per-device* basis. An employee can have ID `5` on the warehouse device and ID `12` on the office device.
- **Night-Shift & Open Attendance Handling**: Automatically pairs check-ins and check-outs. If a check-out is missing, the system gracefully handles the next punch by starting a fresh attendance record (configurable time bounds).
- **Timezone Awareness**: Handles punches in the device's local timezone and converts them accurately to Odoo's UTC storage, ensuring zero offset issues across global deployments.
- **ADMS Command Queue**: For ADMS devices, commands (like reboot or clear log) are securely queued and dispatched the next time the device polls Odoo.
- **ADMS Auto-Registration**: Option to automatically register new devices when they connect via ADMS for the first time.

---

## Installation

1. Install the required `pyzk` python library (only needed if you plan to use PyZK or Hybrid modes):
   ```bash
   pip install pyzk
   ```
2. Copy the `zkteco_biometric_attendance` module into your Odoo `custom_addons` directory.
3. Restart Odoo, go to **Apps**, click **Update Apps List**, search for **ZK Attendance**, and click **Install**.

---

## Configuration & Usage

### 1. PyZK Device Setup
1. Go to **Biometric Attendance > Devices** and create a new device.
2. Set **Connection Mode** to **PyZK**.
3. Fill in the **Device IP** and **Port** (default is 4370).
4. Set the **Device Timezone** to match the actual physical timezone configured on the device hardware. This is critical for correct UTC conversion.
5. Click **Test Connection** to verify connectivity.
6. Make sure the scheduled action `"ZK Attendance: Sync PyZK/Hybrid Devices"` is active. It polls devices every 2 minutes by default.

### 2. ADMS Device Setup
1. Go to **Biometric Attendance > Devices** and create a new device.
2. Set **Connection Mode** to **ADMS**.
3. Set the **Device Timezone** and **Save**.
4. In the device's hardware menu (usually under *Comm. -> Cloud Server Setting*), set the Server Address to your Odoo instance URL/IP, and the port. The device will call `/iclock/cdata` on its own.
5. *(Optional)* To allow unknown devices to self-register on first contact, go to **Biometric Attendance > Configuration > Settings** and enable **ADMS Auto Register**.

### 3. Employee Mapping
1. Go to an employee's form and click the **Biometric IDs** smart button, or navigate to **Biometric Attendance > User Mappings**.
2. Add a mapping record for each device the employee uses, specifying the `Device User ID` exactly as it appears on that specific biometric machine.

### 4. Device Commands
- **PyZK Devices**: Executing commands like "Clear Device Log" happens immediately over the open TCP connection.
- **ADMS Devices**: Commands are pushed to a queue. Use the **Queue Reboot** or **Queue Clear Log** buttons. The device will pick up the command on its next `/iclock/getrequest` poll. Monitor the status under **Command Queue**.

---

## Developer Guide & Extensibility

This module is designed to be a solid, unopinionated foundation. It deliberately avoids enforcing specific business rules (like overtime slab rounding, late-entry penalties, or approval workflows) because these vary wildly between companies.

To add your own business rules, simply create a small custom module that depends on `zkteco_biometric_attendance` and overrides the `_finalize_attendance` hook:

```python
from odoo import models

class ZkAttendanceProcessor(models.AbstractModel):
    _inherit = "zk.attendance.processor"

    def _finalize_attendance(self, attendance, log):
        super()._finalize_attendance(attendance, log)
        # Your custom logic here:
        # e.g., check if the employee was late based on their schedule
        # e.g., set the state to 'draft' requiring HR approval
        # e.g., calculate and split regular hours vs overtime
```

