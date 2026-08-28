# -*- coding: utf-8 -*-
"""
Thin wrapper around the third-party `zk` (pyzk) library.

Every pyzk call goes through this class and nowhere else in the codebase.
That is deliberate: pyzk has forks (pyzk, pyzk2, in-house patched forks)
with slightly different signatures, and isolating it here means swapping
the library later is a one-file change instead of an addon-wide refactor.

The `zk` package is imported lazily inside __init__, not at module import
time, so that:
  * the addon still loads cleanly on an ADMS-only deployment where the
    library was never installed, and
  * a broken pyzk install surfaces as a clear UserError when someone
    actually tries to use PyZK, not as a silent addon load failure.
"""
import logging

_logger = logging.getLogger(__name__)


class PyZKConnectionError(Exception):
    pass


class PyZKService:

    def __init__(self, device):
        try:
            from zk import ZK
        except ImportError as exc:
            raise PyZKConnectionError(
                "The 'zk' (pyzk) python package is not installed on this "
                "server. Run: pip install pyzk"
            ) from exc

        self.device = device
        self._zk = ZK(
            device.device_ip,
            port=device.device_port or 4370,
            timeout=device.zk_timeout or 5.0,
            password=device.zk_password or 0,
            force_udp=device.zk_force_udp,
            ommit_ping=device.zk_ommit_ping,
        )
        self._conn = None

    # -------------------------------------------------------------- lifecycle --
    def connect(self):
        if not self.device.device_ip:
            raise PyZKConnectionError("Device IP is not configured.")
        try:
            self._conn = self._zk.connect()
        except Exception as exc:  # noqa: BLE001 - library raises plain Exception
            raise PyZKConnectionError(f"Could not connect to {self.device.device_ip}: {exc}") from exc
        return self._conn

    def disconnect(self):
        if self._conn:
            try:
                self._conn.disconnect()
            except Exception:  # noqa: BLE001 - best-effort on teardown
                _logger.warning("Error disconnecting from device %s", self.device.name, exc_info=True)
            finally:
                self._conn = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    def _ensure_connected(self):
        if not self._conn:
            raise PyZKConnectionError("Not connected. Call connect() first.")

    # ---------------------------------------------------------------- reads --
    def get_device_info(self):
        self._ensure_connected()
        return {
            "serial_number": self._conn.get_serialnumber(),
            "firmware_version": self._conn.get_firmware_version(),
            "platform": self._conn.get_platform(),
            "device_name": self._conn.get_device_name(),
            "user_count": len(self._conn.get_users() or []),
        }

    def get_users(self):
        self._ensure_connected()
        return self._conn.get_users()

    def get_attendance(self):
        self._ensure_connected()
        return self._conn.get_attendance()

    # --------------------------------------------------------------- writes --
    def clear_attendance(self):
        self._ensure_connected()
        return self._conn.clear_attendance()

    def set_user(self, uid, name, privilege, password="", group_id="", user_id=""):
        self._ensure_connected()
        return self._conn.set_user(
            uid=uid, name=name, privilege=privilege,
            password=password, group_id=group_id, user_id=user_id,
        )

    def restart_device(self):
        self._ensure_connected()
        return self._conn.restart()

    def enable_device(self):
        self._ensure_connected()
        return self._conn.enable_device()

    def disable_device(self):
        self._ensure_connected()
        return self._conn.disable_device()

    def voice_test(self):
        self._ensure_connected()
        return self._conn.test_voice()
