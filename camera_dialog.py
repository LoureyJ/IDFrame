"""Choose Windows-recognized cameras and capture a local, owned portrait frame."""

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
)
from PySide6.QtMultimedia import (
    QCamera,
    QMediaDevices,
    QMediaCaptureSession,
    QVideoFrame,
)
from camera_view import CameraView
from portrait_guides import PRC_REMINDERS, GUIDE_HELP

from qt_preview import qt_to_image


class CameraDialog(QDialog):
    """Own camera selection, viewfinder frames and device cleanup for one session."""

    def __init__(
        self,
        parent=None,
        *,
        selected_device_id=None,
        output_size=(1200, 1200),
        eye=0.38,
        headroom=0.08,
    ):
        """Enumerate real device identities without assuming built-in/USB index numbers."""
        super().__init__(parent)
        self.setWindowTitle("IDFrame — Camera")
        available = QApplication.primaryScreen().availableGeometry()
        self.resize(min(800, available.width() - 20), min(620, available.height() - 45))
        self.photo, self.camera, self._frame = None, None, None
        self.selected_device_id = selected_device_id
        self._generation, self._closed = 0, False
        self._reviewing = False
        self._frame_callback = None
        self._inputs = []
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Choose camera"))
        self.device_combo = QComboBox()
        self.device_combo.setAccessibleName("Camera device")
        layout.addWidget(self.device_combo)
        self.video = CameraView(
            self, output_size=output_size, eye=eye, headroom=headroom
        )
        self.video.setMinimumSize(200, 150)
        layout.addWidget(self.video, 1)
        reminders = QLabel(PRC_REMINDERS)
        reminders.setWordWrap(True)
        reminders.setToolTip(
            GUIDE_HELP
            + " Keep the whole head and shoulders visible. Adjust Zoom after removal."
        )
        layout.addWidget(reminders)
        self.status = QLabel("Looking for cameras…")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.capture_button = QPushButton("Capture Photo")
        self.capture_button.setProperty("accent", True)
        self.capture_button.setEnabled(False)
        self.capture_button.clicked.connect(self.capture_photo)
        buttons.addWidget(self.capture_button)
        self.use_button = QPushButton("Use Photo")
        self.use_button.setProperty("accent", True)
        self.use_button.clicked.connect(self.use_photo)
        self.use_button.hide()
        buttons.addWidget(self.use_button)
        self.retake_button = QPushButton("Retake")
        self.retake_button.clicked.connect(self.retake)
        self.retake_button.hide()
        buttons.addWidget(self.retake_button)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)
        self.session = QMediaCaptureSession(self)
        self.session.setVideoSink(self.video.videoSink())
        self.devices = QMediaDevices(self)
        self.devices.videoInputsChanged.connect(self.refresh_devices)
        self.device_combo.currentIndexChanged.connect(self.select_camera)
        self.startup_timer = QTimer(self)
        self.startup_timer.setSingleShot(True)
        self.startup_timer.setInterval(10000)
        self.startup_timer.timeout.connect(self._startup_timeout)
        self.refresh_devices()

    def refresh_devices(self):
        """Retain the chosen ID on hotplug, or select the operating-system default."""
        if self._closed or self._reviewing:
            return
        self._inputs = QMediaDevices.videoInputs()
        previous = self.selected_device_id
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        descriptions = [device.description() for device in self._inputs]
        for number, device in enumerate(self._inputs, 1):
            label = device.description()
            if descriptions.count(label) > 1:
                label += f" ({number})"
            self.device_combo.addItem(label, bytes(device.id()))
        index = next(
            (i for i, d in enumerate(self._inputs) if bytes(d.id()) == previous),
            next(
                (i for i, d in enumerate(self._inputs) if d.isDefault()),
                0 if self._inputs else -1,
            ),
        )
        self.device_combo.setCurrentIndex(index)
        self.device_combo.setEnabled(bool(self._inputs))
        self.device_combo.blockSignals(False)
        if (
            index >= 0
            and bytes(self._inputs[index].id()) == previous
            and self.camera is not None
        ):
            return
        self.select_camera(index)

    def select_camera(self, index):
        """Release the old device before starting the newly selected camera."""
        if self._reviewing:
            return
        self._stop_camera()
        if not 0 <= index < len(self._inputs):
            self.selected_device_id = None
            self.status.setText(
                "No camera found. Connect a USB camera or enable your built-in camera."
            )
            return
        device = self._inputs[index]
        self.selected_device_id = bytes(device.id())
        self.camera = QCamera(device, self)
        self.camera.errorOccurred.connect(self._camera_error)
        self.camera.activeChanged.connect(self._active_changed)
        self.session.setCamera(self.camera)
        self._frame_callback = (
            lambda frame, token=self._generation: self._receive_frame(frame, token)
        )
        self.video.videoSink().videoFrameChanged.connect(self._frame_callback)
        self.status.setText("Starting " + device.description() + "…")
        self.startup_timer.start()
        self.camera.start()

    def _receive_frame(self, frame, generation):
        """Keep the latest source frame while rejecting events from a previous device."""
        if (
            self._closed
            or generation != self._generation
            or self.camera is None
            or not self.camera.isActive()
            or not frame.isValid()
        ):
            return
        self._frame = QVideoFrame(frame)
        self.startup_timer.stop()
        self.capture_button.setEnabled(True)
        self.status.setText("Ready — position the person, then capture a photo.")

    def _active_changed(self, active):
        """Disable capture whenever a camera stops producing live input."""
        if not active and not self._reviewing:
            self._frame = None
            self.capture_button.setEnabled(False)
            self.status.setText(
                "Camera stopped. Choose another camera or reopen this window."
            )

    def _camera_error(self, error, message):
        """Explain busy/permission failures without losing the main portrait document."""
        if self._reviewing:
            return
        self._stop_camera()
        self.status.setText(
            message
            + " — Close other camera apps and check Windows camera privacy access. "
            "Choose another camera or reopen this window to retry."
        )

    def _startup_timeout(self):
        """Provide actionable feedback if a driver starts but never delivers a frame."""
        if self._frame is None and not self._closed and not self._reviewing:
            self.status.setText(
                "No camera frames received. Check the lens cover, Windows camera "
                "privacy access, and whether another app is using this device."
            )

    def capture_photo(self):
        """Copy source-frame pixels into a portrait without saving a temporary image."""
        if self._frame is None or self.camera is None or not self.camera.isActive():
            return
        image = self._frame.toImage()
        if image.isNull():
            self.status.setText(
                "This frame could not be read. Wait a moment and capture again."
            )
            return
        self.photo = qt_to_image(image).convert("RGB")
        self._reviewing = True
        self._stop_camera()
        self.video.show_review(image)
        self.device_combo.setEnabled(False)
        self.capture_button.hide()
        self.use_button.show()
        self.use_button.setDefault(True)
        self.retake_button.show()
        self.setWindowTitle("IDFrame — Review photo")
        self.status.setText(
            "Review your photo. Use Photo keeps it; Retake returns to the camera. Guides are not included."
        )

    def use_photo(self):
        """Accept the captured source only after an explicit review decision."""
        if self._reviewing and self.photo is not None:
            self.accept()

    def retake(self):
        """Discard the pending still and reopen the selected device if available."""
        if not self._reviewing:
            return
        self.photo = None
        self._reviewing = False
        self.video.show_live()
        self.use_button.hide()
        self.retake_button.hide()
        self.capture_button.show()
        self.setWindowTitle("IDFrame — Camera")
        self.refresh_devices()

    def _stop_camera(self):
        """Invalidate queued frames, detach the capture session and release the device."""
        self._generation += 1
        self.startup_timer.stop()
        self._frame = None
        self.capture_button.setEnabled(False)
        if self._frame_callback is not None:
            self.video.videoSink().videoFrameChanged.disconnect(self._frame_callback)
            self._frame_callback = None
        if self.camera is not None:
            camera, self.camera = self.camera, None
            camera.errorOccurred.disconnect(self._camera_error)
            camera.activeChanged.disconnect(self._active_changed)
            self.session.setCamera(None)
            camera.stop()
            camera.deleteLater()

    def done(self, result):
        """Release the camera on Capture, Cancel, Escape and window close alike."""
        self._closed = True
        self._stop_camera()
        if result != QDialog.DialogCode.Accepted:
            self.photo = None
        super().done(result)
