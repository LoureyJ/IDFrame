"""Show the receive QR code and hand the uploaded photo back to the workspace."""

import math
import ipaddress
import threading
import time

import qrcode
from PySide6.QtCore import Qt, QTimer, Signal, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtNetwork import QNetworkInterface
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from phone_transfer import PhoneTransfer
from qt_preview import image_to_qt


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
        self._receiver_id = 0
        self._finished = False
        layout = QVBoxLayout(self)
        instructions = QLabel(
            "No Internet is needed. Connect both devices to the same Wi-Fi, "
            "then scan the QR code and send a photo."
        )
        self.instructions = instructions
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        self.qr = QLabel()
        self.qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.qr)
        self.address = QLabel()
        self.address.setWordWrap(True)
        self.address.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.address)
        self.status = QLabel("Starting receiver…")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.hotspot_button = QPushButton("Use This PC’s Hotspot")
        self.hotspot_button.clicked.connect(self._prepare_hotspot)
        layout.addWidget(self.hotspot_button)
        self.open_settings_button = QPushButton("Open Mobile Hotspot Settings")
        self.open_settings_button.clicked.connect(self._open_hotspot_settings)
        self.open_settings_button.hide()
        layout.addWidget(self.open_settings_button)
        self.start_hotspot_button = QPushButton("Start Hotspot Transfer")
        self.start_hotspot_button.clicked.connect(self._start_hotspot_receiver)
        self.start_hotspot_button.hide()
        layout.addWidget(self.start_hotspot_button)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setMinimumWidth(375)
        self.timer = QTimer(self, interval=250)
        self.timer.timeout.connect(self._update_countdown)
        self.ready.connect(self._receiver_ready)
        self.received.connect(self._accept_photo)
        self.unavailable.connect(self._show_unavailable)
        self._start_receiver()

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

    def _prepare_hotspot(self):
        """Pause the current receiver and present Windows hotspot setup steps."""
        if self.session is not None:
            self.session.close()
        self._receiver_id += 1
        self.timer.stop()
        self.qr.clear()
        self.address.clear()
        self.instructions.setText(
            "Turn on Mobile Hotspot on this PC, then connect your phone to its "
            "Wi-Fi network. Return here and start the hotspot transfer QR. "
            "Internet access is not required."
        )
        self.hotspot_button.hide()
        self.open_settings_button.show()
        self.start_hotspot_button.show()
        self.status.setText("Enable the hotspot and connect your phone.")
        self._open_hotspot_settings()

    def _open_hotspot_settings(self):
        """Open the built-in Windows Mobile Hotspot settings page."""
        if not QDesktopServices.openUrl(QUrl("ms-settings:network-mobilehotspot")):
            self.status.setText(
                "Open Windows Settings → Network & Internet → Mobile hotspot."
            )

    def _start_hotspot_receiver(self):
        """Bind the transfer session to the active Windows hotspot adapter."""
        address = detect_mobile_hotspot_ip()
        if address is None:
            self.status.setText(
                "IDFrame could not find an active PC hotspot. Turn on Mobile "
                "Hotspot in Windows Settings, then try again."
            )
            return
        self.start_hotspot_button.setEnabled(False)
        self.status.setText("Starting the local hotspot receiver…")
        self._start_receiver(address)

    def _receiver_ready(self, result):
        """Show a QR only when it belongs to the most recent receiver session."""
        receiver_id, url = result
        if receiver_id == self._receiver_id:
            self._show_code(url)

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

    def _show_code(self, url):
        """Render a high-contrast QR code with its quiet zone intact."""
        if self._finished:
            return
        image = qrcode.make(url, box_size=6, border=4).get_image().convert("RGBA")
        self.qr.setPixmap(QPixmap.fromImage(image_to_qt(image)))
        self.address.setText(url)
        self._update_countdown()
        self.timer.start()

    def _update_countdown(self):
        """Show how long the QR code remains usable."""
        seconds = max(0, math.ceil(self.session.deadline - time.monotonic()))
        self.status.setText(f"Expires in {seconds // 60}:{seconds % 60:02d}")

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
        self.start_hotspot_button.setEnabled(True)
        self.status.setText(message)

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
        if self.session is not None:
            self.session.close()
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
