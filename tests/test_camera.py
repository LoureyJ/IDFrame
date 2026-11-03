"""Camera selection, capture and cleanup contracts without accessing real devices."""

import unittest
from unittest.mock import patch

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage, QColor
from PySide6.QtWidgets import QWidget

import test_qt_app as fixtures
from camera_dialog import CameraDialog


class Device:
    """Represent an enumerated Windows camera with stable ID and display name."""

    def __init__(self, identity, name, default=False):
        """Keep hardware identity separate from a possibly duplicate friendly name."""
        self.identity, self.name, self.default = identity, name, default

    def id(self):
        """Return the driver-provided persistent device identifier."""
        return self.identity

    def description(self):
        """Return the user-facing device label."""
        return self.name

    def isDefault(self):
        """Indicate the operating system's preferred camera."""
        return self.default


class Devices(QObject):
    """Simulate enumeration and hotplug events without requesting camera access."""

    videoInputsChanged = Signal()
    inputs = []

    @staticmethod
    def videoInputs():
        """Return the current controlled hardware inventory."""
        return Devices.inputs


class Camera(QObject):
    """Simulate asynchronous camera lifecycle for deterministic ownership checks."""

    activeChanged = Signal(bool)
    errorOccurred = Signal(object, str)

    def __init__(self, device, parent=None):
        """Bind one hardware device without opening it."""
        super().__init__(parent)
        self.device, self.active, self.stopped = device, False, False

    def start(self):
        """Mark a fake capture session as running."""
        self.active = True
        self.activeChanged.emit(True)

    def stop(self):
        """Record that the device was released."""
        self.active, self.stopped = False, True

    def isActive(self):
        """Expose whether frames may currently be consumed."""
        return self.active


class Sink(QObject):
    """Emit controlled video frames to the capture dialog."""

    videoFrameChanged = Signal(object)


class Video(QWidget):
    """Stand in for the video widget while preserving real Qt layout behavior."""

    def __init__(self, parent=None):
        """Own a fake frame sink for this viewfinder."""
        super().__init__(parent)
        self.sink = Sink(self)

    def videoSink(self):
        """Expose the viewfinder's frame source."""
        return self.sink


class Session(QObject):
    """Keep camera attachment separate from fake media-device ownership."""

    def setVideoOutput(self, video):
        """Remember the output widget without requiring a native backend."""
        self.video = video

    def setCamera(self, camera):
        """Attach or detach a device from this capture session."""
        self.camera = camera


class Frame:
    """Supply an owned full-frame image rather than a scaled preview screenshot."""

    def __init__(self, image):
        """Keep the source image for conversion tests."""
        self.image = image

    def isValid(self):
        """Reject empty video frames before enabling Capture."""
        return not self.image.isNull()

    def toImage(self):
        """Return captured camera pixels at their original stream resolution."""
        return self.image.copy()


class CameraTests(unittest.TestCase):
    """Check hotplug, switching, capture, cancellation and camera-error behavior."""

    def setUp(self):
        """Replace only hardware-facing Qt classes while retaining real widgets."""
        Devices.inputs = [
            Device(b"internal", "Integrated camera", True),
            Device(b"usb", "USB camera"),
        ]
        for name, replacement in [
            ("QMediaDevices", Devices),
            ("QCamera", Camera),
            ("QMediaCaptureSession", Session),
            ("QVideoWidget", Video),
            ("QVideoFrame", lambda frame: frame),
        ]:
            manager = patch("camera_dialog." + name, replacement)
            manager.start()
            self.addCleanup(manager.stop)
        self.dialog = CameraDialog()
        self.addCleanup(self.dialog.reject)
        self.addCleanup(self.dialog.deleteLater)

    def test_switch_and_capture_owned_source_pixels_then_release_camera(self):
        """Select USB by ID and capture stream pixels without resizing or mirroring."""
        initial = self.dialog.camera
        self.dialog.device_combo.setCurrentIndex(1)
        self.assertTrue(initial.stopped)
        self.assertEqual(self.dialog.selected_device_id, b"usb")
        camera = self.dialog.camera
        self.assertFalse(self.dialog.capture_button.isEnabled())
        image = QImage(640, 480, QImage.Format.Format_RGB32)
        image.fill(QColor("red"))
        image.setPixelColor(0, 0, QColor("blue"))
        self.dialog.video.videoSink().videoFrameChanged.emit(Frame(image))
        self.assertTrue(self.dialog.capture_button.isEnabled())
        self.dialog.capture_button.click()
        self.assertEqual(self.dialog.photo.size, (640, 480))
        self.assertEqual(self.dialog.photo.getpixel((0, 0)), (0, 0, 255))
        self.assertEqual(self.dialog.photo.getpixel((639, 479)), (255, 0, 0))
        self.assertTrue(camera.stopped)

    def test_hotplug_cancel_and_error_drop_stale_frames(self):
        """Disconnects and errors disable Capture, preserving a clean retry path."""
        original = self.dialog.camera
        old_callback = self.dialog._frame_callback
        self.dialog.camera.errorOccurred.emit(1, "Permission denied")
        self.assertFalse(self.dialog.capture_button.isEnabled())
        self.assertIn("Permission denied", self.dialog.status.text())
        Devices.inputs = [Devices.inputs[1]]
        self.dialog.devices.videoInputsChanged.emit()
        self.assertTrue(original.stopped)
        image = QImage(10, 10, QImage.Format.Format_RGB32)
        old_callback(Frame(image))
        self.assertFalse(self.dialog.capture_button.isEnabled())
        active = self.dialog.camera
        self.dialog.reject()
        self.assertTrue(active.stopped)
        self.assertIsNone(self.dialog.photo)

    def test_no_camera_is_nonfatal_and_plugging_one_in_recovers(self):
        """A missing device gives useful feedback and can appear while the dialog is open."""
        Devices.inputs = []
        self.dialog.devices.videoInputsChanged.emit()
        self.assertIsNone(self.dialog.camera)
        self.assertFalse(self.dialog.capture_button.isEnabled())
        self.assertIn("No camera", self.dialog.status.text())
        Devices.inputs = [Device(b"new", "External webcam")]
        self.dialog.devices.videoInputsChanged.emit()
        self.assertEqual(self.dialog.selected_device_id, b"new")

    def test_enumeration_reordering_preserves_device_without_reopening(self):
        """USB order changes and duplicate labels cannot silently switch the camera."""
        self.dialog.device_combo.setCurrentIndex(1)
        active = self.dialog.camera
        for device in Devices.inputs:
            device.name = "Webcam"
        Devices.inputs.reverse()
        self.dialog.devices.videoInputsChanged.emit()
        self.assertIs(self.dialog.camera, active)
        self.assertFalse(active.stopped)
        self.assertEqual(self.dialog.selected_device_id, b"usb")


class CameraApplicationTests(unittest.TestCase):
    """Captured photos use the existing safe source-loading pipeline."""

    setUp = fixtures.QtAppTests.setUp
    tearDown = fixtures.QtAppTests.tearDown

    def test_camera_button_accepts_capture_and_cancel_preserves_previous_photo(self):
        """Only an accepted camera capture replaces the current document."""
        from PIL import Image
        from types import SimpleNamespace
        from PySide6.QtWidgets import QDialog

        accepted = SimpleNamespace(
            exec=lambda: QDialog.DialogCode.Accepted,
            photo=Image.new("RGB", (640, 480), "blue"),
            selected_device_id=b"usb",
            deleteLater=lambda: None,
        )
        with patch("camera_dialog.CameraDialog", return_value=accepted):
            self.window.camera_button.click()
        self.assertEqual(self.window.photo.size, (640, 480))
        self.assertIsNone(self.window.crop.cutout)
        previous = self.window.photo
        accepted.exec = lambda: QDialog.DialogCode.Rejected
        with patch("camera_dialog.CameraDialog", return_value=accepted):
            self.window.camera_button.click()
        self.assertIs(self.window.photo, previous)


if __name__ == "__main__":
    unittest.main()
