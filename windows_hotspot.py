"""Manage one temporary Windows Mobile Hotspot session for local photo transfer."""

import asyncio
import secrets
import threading

from PySide6.QtCore import QObject, Signal


# Do not start a new dialog's hotspot while a previous session is shutting down.
_HOTSPOT_SESSION_LOCK = threading.Lock()


class WindowsHotspot(QObject):
    """Start, monitor, and stop only the hotspot session owned by this dialog."""

    started = Signal(object)
    connected = Signal()
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop_requested = threading.Event()
        self._disconnect_existing_requested = threading.Event()
        self._thread = None

    def start(self):
        """Start the WinRT tethering worker without blocking the Qt interface."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run,
            name="IDFrame local hotspot",
            daemon=True,
        )
        self._thread.start()

    def stop(self, *, disconnect_existing=False):
        """Stop this transfer's hotspot, optionally disconnecting a reused one."""
        if disconnect_existing:
            self._disconnect_existing_requested.set()
        self._stop_requested.set()

    def _run(self):
        """Run WinRT operations on one worker thread and report startup failures."""
        try:
            # Windows may briefly report an old session as ON while its async stop
            # operation is completing. Serialize the full lifetime across dialogs.
            with _HOTSPOT_SESSION_LOCK:
                asyncio.run(self._manage_session())
        except Exception as error:
            self.failed.emit(self._friendly_error(error))

    async def _manage_session(self):
        """Start a temporary hotspot or reuse an active Windows hotspot safely."""
        from winrt.windows.networking.connectivity import NetworkInformation
        from winrt.windows.networking.networkoperators import (
            NetworkOperatorTetheringManager,
            NetworkOperatorTetheringSessionAccessPointConfiguration,
            TetheringCapability,
            TetheringOperationStatus,
            TetheringOperationalState,
            TetheringWiFiAuthenticationKind,
            TetheringWiFiBand,
        )

        profile = NetworkInformation.get_internet_connection_profile()
        if profile is None:
            raise RuntimeError(
                "Connect this PC to Ethernet or Wi-Fi first. Internet access is not required."
            )

        capability = (
            NetworkOperatorTetheringManager.get_tethering_capability_from_connection_profile(
                profile
            )
        )
        if capability != TetheringCapability.ENABLED:
            if capability == TetheringCapability.DISABLED_BY_SYSTEM_CAPABILITY:
                raise RuntimeError(
                    "Install the latest IDFrame package installer once to enable PC hotspot control."
                )
            raise RuntimeError(
                "Windows or this PC's Wi-Fi adapter does not allow Mobile Hotspot "
                f"({capability.name.replace('_', ' ').lower()})."
            )

        manager = NetworkOperatorTetheringManager.create_from_connection_profile(
            profile
        )
        owns_session = False
        if manager.tethering_operational_state == TetheringOperationalState.ON:
            access_point = manager.get_current_access_point_configuration()
            ssid = access_point.ssid
            passphrase = access_point.passphrase
            if not ssid or not passphrase:
                raise RuntimeError(
                    "The existing Windows hotspot does not expose its Wi-Fi details. Turn it off and try again."
                )
        else:
            session_config = NetworkOperatorTetheringSessionAccessPointConfiguration()
            ssid = "IDFrame-" + secrets.token_hex(3).upper()
            passphrase = secrets.token_hex(8)
            session_config.ssid = ssid
            session_config.passphrase = passphrase
            session_config.band = TetheringWiFiBand.TWO_POINT_FOUR_GIGAHERTZ
            session_config.authentication_kind = TetheringWiFiAuthenticationKind.WPA2

            result = await manager.start_tethering_async(session_config)
            if result.status == TetheringOperationStatus.SUCCESS:
                owns_session = True
            elif result.status == TetheringOperationStatus.ALREADY_ON:
                access_point = manager.get_current_access_point_configuration()
                ssid = access_point.ssid
                passphrase = access_point.passphrase
                if not ssid or not passphrase:
                    raise RuntimeError(
                        "Windows already has a hotspot running, but its Wi-Fi details are unavailable."
                    )
            else:
                detail = result.additional_error_message or result.status.name
                raise RuntimeError(f"Windows could not start the hotspot: {detail}")

        try:
            self.started.emit({"ssid": ssid, "passphrase": passphrase})
            while not self._stop_requested.is_set():
                if manager.client_count > 0:
                    self.connected.emit()
                    break
                await asyncio.sleep(0.35)
            while not self._stop_requested.is_set():
                await asyncio.sleep(0.2)
        finally:
            if owns_session or self._disconnect_existing_requested.is_set():
                await manager.stop_tethering_async()

    @staticmethod
    def _friendly_error(error):
        """Turn WinRT startup failures into useful transfer-dialog guidance."""
        message = str(error).strip()
        if "0x80070005" in message or "access is denied" in message.lower():
            return (
                "Windows denied hotspot access. Reinstall IDFrame using the updated "
                "installer and accept the IDFrame package trust prompt."
            )
        return message or "Windows could not start the local hotspot."
