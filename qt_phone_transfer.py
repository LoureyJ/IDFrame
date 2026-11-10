"""Show the receive QR code and hand the uploaded photo back to the workspace."""

import math
import ipaddress
import threading
import time

import qrcode
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkInterface
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)

from phone_transfer import PhoneTransfer
from qt_preview import image_to_qt
from windows_hotspot import WindowsHotspot


class PhoneTransferDialog(QDialog):
    """Own the receive session for as long as the modal dialog is open."""

    ready = Signal(object)
    received = Signal(object)
    unavailable = Signal(object)

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Receive from Phone")
        self.photo = None
        self.session = None
        self.hotspot = None
        self._receiver_id = 0
        self._finished = False
        self._upload_url = None
        self._phone_connected = False
        self._hotspot_credentials = None
        self._hotspot_ip_deadline = 0
        layout = QVBoxLayout(self)
        instructions = QLabel("IDFrame is preparing a private Wi-Fi connection…")
        self.instructions = instructions
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        self.stage = QLabel("Step 1 of 2 · Connect to IDFrame Wi-Fi")
        self.stage.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.stage)
        self.qr = QLabel()
        self.qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.qr)
        self.address = QLabel()
        self.address.setWordWrap(True)
        self.address.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.address)
        self.status = QLabel("Starting this PC’s hotspot…")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setMinimumWidth(375)
        self.timer = QTimer(self, interval=250)
        self.timer.timeout.connect(self._update_countdown)
        self.address_timer = QTimer(self, interval=350)
        self.address_timer.timeout.connect(self._find_hotspot_address)
        self.ready.connect(self._receiver_ready)
        self.received.connect(self._accept_photo)
        self.unavailable.connect(self._show_unavailable)
        self.hotspot = WindowsHotspot(self)
        self.hotspot.started.connect(self._hotspot_started)
        self.hotspot.connected.connect(self._hotspot_connected)
        self.hotspot.failed.connect(self._hotspot_failed)
        self.hotspot.start()

    def _start_receiver(self, address=None):
        """Start a one-use receiver on the selected local network interface."""
        self._receiver_id += 1
        receiver_id = self._receiver_id
        session = self.session = PhoneTransfer(address=address)
        threading.Thread(
            target=self._run_receiver,
            args=(session, receiver_id),
            name="IDFrame phone receiver",
            daemon=True,
        ).start()

    def _hotspot_started(self, credentials):
        """Show the Wi-Fi join QR and wait for the hotspot adapter to appear."""
        if self._finished:
            return
        self._hotspot_credentials = credentials
        self._hotspot_ip_deadline = time.monotonic() + 20
        self.instructions.setText(
            "Scan this QR code with the phone’s camera to join IDFrame Wi-Fi. "
            "When the phone connects, this QR changes to the photo-transfer code. "
            "Internet access is not required."
        )
        self._show_wifi_code(credentials["ssid"], credentials["passphrase"])
        self.status.setText("Waiting for the phone to connect to this PC…")
        self.address_timer.start()

    def _show_wifi_code(self, ssid, passphrase):
        """Display the temporary hotspot credentials as a standards-based Wi-Fi QR."""
        qr_payload = f"WIFI:T:WPA;S:{ssid};P:{passphrase};;"
        image = qrcode.make(qr_payload, box_size=6, border=4).get_image().convert("RGBA")
        self.qr.setPixmap(QPixmap.fromImage(image_to_qt(image)))
        self.address.setText(f"Wi-Fi network: {ssid}\nPassword: {passphrase}")

    def _find_hotspot_address(self):
        """Wait briefly for Windows to assign the hotspot adapter its local IPv4."""
        if self._finished:
            self.address_timer.stop()
            return
        address = detect_mobile_hotspot_ip()
        if not address:
            if time.monotonic() >= self._hotspot_ip_deadline:
                self.address_timer.stop()
                self.qr.clear()
                self.address.clear()
                self.status.setText(
                    "Windows started the hotspot, but IDFrame could not find its "
                    "local network address. Close this window and try again."
                )
                if self.hotspot is not None:
                    self.hotspot.stop()
            return
        self.address_timer.stop()
        self.status.setText("Hotspot ready. Waiting for your phone to connect…")
        self._start_receiver(address)

    def _hotspot_connected(self):
        """Switch to the upload QR only after Windows detects the phone connection."""
        if self._finished:
            return
        self._phone_connected = True
        self._show_upload_code_if_ready()

    def _hotspot_failed(self, message):
        """Report Windows tethering limitations without losing the current workspace."""
        if self._finished:
            return
        self.address_timer.stop()
        self.qr.clear()
        self.address.clear()
        self.status.setText(message)
        self.instructions.setText(
            "Connect this PC to Ethernet or Wi-Fi and make sure Mobile Hotspot is "
            "allowed for its Wi-Fi adapter. Internet access is not needed."
        )

    def _receiver_ready(self, result):
        """Show a QR only when it belongs to the most recent receiver session."""
        receiver_id, url = result
        if receiver_id == self._receiver_id:
            self._upload_url = url
            self._update_countdown()
            self.timer.start()
            self._show_upload_code_if_ready()

    def _show_upload_code_if_ready(self):
        """Render the second-step upload code after both prerequisites are met."""
        if not self._phone_connected or not self._upload_url or self._finished:
            return
        image = qrcode.make(self._upload_url, box_size=6, border=4).get_image().convert("RGBA")
        self.qr.setPixmap(QPixmap.fromImage(image_to_qt(image)))
        self.stage.setText("Step 2 of 2 · Send the photo")
        self.instructions.setText(
            "Phone connected. Scan this new QR code with the phone’s camera, "
            "choose the photo, then tap Send photo."
        )
        self.address.setText(self._upload_url)
        self.status.setText("The photo will be processed automatically after transfer.")

    def _run_receiver(self, session, receiver_id):
        """Start the network listener off the GUI thread."""
        def emit(signal, value):
            try:
                signal.emit((receiver_id, value))
            except RuntimeError:
                pass  # The workspace may have closed while the receiver was stopping.

        try:
            session.run(
                lambda url: emit(self.ready, url),
                lambda photo: emit(self.received, photo),
                lambda: emit(
                    self.unavailable,
                    "QR code expired. Reopen Receive from Phone to try again.",
                ),
            )
        except OSError:
            emit(
                self.unavailable,
                "Could not start the receiver. Check this PC's network connection.",
            )

    def _update_countdown(self):
        """Show how long the QR code remains usable."""
        seconds = max(0, math.ceil(self.session.deadline - time.monotonic()))
        remaining = f"{seconds // 60}:{seconds % 60:02d}"
        if self._phone_connected and self._upload_url:
            self.status.setText(f"Scan the upload QR · expires in {remaining}")
        else:
            self.status.setText(f"Waiting for phone connection · expires in {remaining}")

    def _show_unavailable(self, message):
        """Remove a QR code that can no longer be used."""
        receiver_id, message = message
        if receiver_id != self._receiver_id:
            return
        if self._finished:
            return
        self.timer.stop()
        self.qr.clear()
        self.address.clear()
        self.status.setText(message)
        if self.hotspot is not None:
            self.hotspot.stop()

    def _accept_photo(self, result):
        """Ignore queued results once the matching dialog has finished."""
        receiver_id, photo = result
        if not self._finished and receiver_id == self._receiver_id:
            self.photo = photo
            self.accept()

    def done(self, result):
        """Cancel the session on every dialog exit path."""
        self._finished = True
        self.timer.stop()
        self.address_timer.stop()
        if self.session is not None:
            self.session.close()
        if self.hotspot is not None:
            self.hotspot.stop(
                disconnect_existing=result == QDialog.DialogCode.Accepted
            )
        super().done(result)


def detect_mobile_hotspot_ip():
    """Find a private IPv4 address belonging to Windows Mobile Hotspot."""
    candidates = []
    for interface in QNetworkInterface.allInterfaces():
        flags = interface.flags()
        if not flags & QNetworkInterface.InterfaceFlag.IsUp:
            continue
        if flags & QNetworkInterface.InterfaceFlag.IsLoopBack:
            continue
        name = (interface.name() + " " + interface.humanReadableName()).lower()
        hotspot_interface = (
            "local area connection*" in name
            or "wi-fi direct" in name
            or "wifi direct" in name
            or "hotspot" in name
        )
        for entry in interface.addressEntries():
            try:
                address = entry.ip().toString()
                parsed = ipaddress.ip_address(address)
            except ValueError:
                continue
            if not isinstance(parsed, ipaddress.IPv4Address):
                continue
            if not parsed.is_private or parsed.is_link_local or parsed.is_loopback:
                continue
            if str(parsed) == "192.168.137.1":
                return str(parsed)
            if hotspot_interface:
                candidates.append(str(parsed))
    return candidates[0] if candidates else None
