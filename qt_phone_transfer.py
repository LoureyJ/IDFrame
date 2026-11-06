"""Show the receive QR code and hand the uploaded photo back to the workspace."""

import math
import threading
import time

import qrcode
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout

from phone_transfer import PhoneTransfer
from qt_preview import image_to_qt


class PhoneTransferDialog(QDialog):
    """Own the receive session for as long as the modal dialog is open."""

    ready = Signal(str)
    received = Signal(object)
    unavailable = Signal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Receive from Phone")
        self.photo = None
        self.session = PhoneTransfer()
        self._finished = False
        layout = QVBoxLayout(self)
        instructions = QLabel(
            "Scan with your phone camera, choose a photo, then tap Send photo. "
            "Connect both devices to the same trusted network. "
            "Guest Wi-Fi or Windows Firewall may block the connection."
        )
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
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setMinimumWidth(375)
        self.timer = QTimer(self, interval=250)
        self.timer.timeout.connect(self._update_countdown)
        self.ready.connect(self._show_code)
        self.received.connect(self._accept_photo)
        self.unavailable.connect(self._show_unavailable)
        threading.Thread(target=self._run_receiver, name="IDFrame phone receiver", daemon=True).start()

    def _run_receiver(self):
        """Start the network listener off the GUI thread."""
        def emit(signal, value):
            try:
                signal.emit(value)
            except RuntimeError:
                pass  # The workspace may have closed while the receiver was stopping.

        try:
            self.session.run(
                lambda url: emit(self.ready, url),
                lambda photo: emit(self.received, photo),
                lambda: emit(self.unavailable, "QR code expired. Reopen Receive from Phone to try again."),
            )
        except OSError:
            emit(self.unavailable, "Could not start the receiver. Check this PC's network connection.")

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
        if self._finished:
            return
        self.timer.stop()
        self.qr.clear()
        self.address.clear()
        self.status.setText(message)

    def _accept_photo(self, photo):
        """Ignore queued results once the matching dialog has finished."""
        if not self._finished:
            self.photo = photo
            self.accept()

    def done(self, result):
        """Cancel the session on every dialog exit path."""
        self._finished = True
        self.timer.stop()
        self.session.close()
        super().done(result)
