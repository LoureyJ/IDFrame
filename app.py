"""Qt portrait studio with offline inference and cached, responsive image previews."""

import os
from pathlib import Path
import sys

from PIL import Image
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QFont, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QButtonGroup,
    QRadioButton,
    QScrollArea,
    QSlider,
    QProgressBar,
    QFileDialog,
    QMessageBox,
)

from app_version import VERSION
from alignment import OfflineAligner
from portrait import (
    PortraitRemover,
    AutomaticPortraitRemover,
    load_photo,
    frame_portrait,
    save_portrait,
)
from photo_naming import portrait_filename, available_photo_path
from windows_branding import set_taskbar_identity, sync_installed_shortcuts
from qt_jobs import JobPool
from qt_preview import PhotoPreview, qt_to_image
from qt_theme import apply_theme, load_theme, save_theme
from qt_dialogs import ask_person_name, changelog_dialog

ROOT = Path(__file__).resolve().parent


class PortraitApp(QMainWindow):
    """Coordinate Qt controls while workers handle image preparation and inference."""

    def __init__(self, *, preferences_path=None, sync_shortcuts=True):
        """Create the document, shared models, job pool, and branded desktop workspace."""
        super().__init__()
        set_taskbar_identity()
        self.preferences_path = preferences_path
        self.theme = load_theme(preferences_path)
        self.photo = self.result = self.path = None
        self.person_name = ""
        self.busy, self.generation = False, 0
        self._close_timer_pending = False
        self.editor = self.changelog_window = None
        self.jobs = JobPool(self)
        self.remover = PortraitRemover()
        self.aligner = OfflineAligner()
        hair = PortraitRemover(mode="fine_hair")
        self.removers = {
            "Auto": AutomaticPortraitRemover(self.remover, hair),
            "Protect person": self.remover,
            "Fine hair": hair,
        }
        self.removal_mode, self.active_mode = "Auto", None
        self.setWindowTitle(f"IDFrame v{VERSION} — Offline Background Remover")
        self.setWindowIcon(QIcon(str(ROOT / "assets/portrait-studio.ico")))
        available = QApplication.primaryScreen().availableGeometry()
        width, height = available.width() - 16, available.height() - 40
        self.setMinimumSize(min(860, width), min(560, height))
        self.resize(min(1240, width), min(780, height))
        self._build_interface()
        apply_theme(self.theme)
        self.theme_buttons[self.theme].setChecked(True)
        self.paste_shortcut = QShortcut(QKeySequence.StandardKey.Paste, self)
        self.paste_shortcut.activated.connect(self.paste_photo)
        self._set_busy(False)
        if sync_shortcuts:
            self.jobs.submit(
                lambda: sync_installed_shortcuts(ROOT / "assets"), self._branding_done
            )

    def _branding_done(self, value, error):
        """Report shortcut refresh errors without interrupting the photo workflow."""
        if error is not None:
            import logging

            logging.getLogger(__name__).warning("Shortcut refresh failed: %s", error)

    def _build_interface(self):
        """Build rounded photo cards and a scrollable inspector with Save kept visible."""
        central = QWidget()
        page = QVBoxLayout(central)
        compact = self.width() < 860
        margin = 12 if compact else 20
        page.setContentsMargins(margin, 18, margin, 14)
        page.setSpacing(14)
        self.setCentralWidget(central)
        header = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(self.windowIcon().pixmap(34, 34))
        title = QLabel("IDFrame")
        title.setFont(QFont("Segoe UI", 23, QFont.Weight.Bold))
        for widget in (icon, title, QLabel("v" + VERSION)):
            header.addWidget(widget)
        header.addStretch()
        self.theme_buttons = {}
        self.theme_group = QButtonGroup(self)
        for name in ("Light", "Dark"):
            button = QPushButton(name)
            button.setCheckable(True)
            self.theme_group.addButton(button)
            button.clicked.connect(
                lambda checked=False, value=name: self.change_theme(value)
            )
            self.theme_buttons[name] = button
            header.addWidget(button)
        changelog = QPushButton("Changelog")
        changelog.clicked.connect(self.open_changelog)
        header.addWidget(changelog)
        page.addLayout(header)
        toolbar = QHBoxLayout()
        self.open_button = QPushButton("Open Photo")
        self.open_button.clicked.connect(self.open_photo)
        self.paste_button = QPushButton("Paste · Ctrl+V")
        self.paste_button.clicked.connect(self.paste_photo)
        self.auto_skew_button = QPushButton("Auto-skew")
        self.auto_skew_button.setToolTip(
            "Estimate eye-level rotation offline. Fine-tune with Rotation if needed."
        )
        self.auto_skew_button.clicked.connect(self.auto_skew)
        self.edit_button = QPushButton("Edit")
        self.edit_button.clicked.connect(self.open_editor)
        for button, color in (
            (self.open_button, "blue"),
            (self.paste_button, "teal"),
            (self.auto_skew_button, "gold"),
            (self.edit_button, "purple"),
        ):
            button.setProperty("actionColor", color)
            toolbar.addWidget(button)
        toolbar.addStretch()
        privacy = QLabel("Your photos stay on this computer")
        privacy.setWordWrap(True)
        toolbar.addWidget(privacy)
        page.addLayout(toolbar)
        workspace = QHBoxLayout()
        workspace.setSpacing(12)
        self.before, self.crop = PhotoPreview(self.jobs, framing=False), PhotoPreview(
            self.jobs
        )
        for text, preview in (("Original", self.before), ("2 × 2 Preview", self.crop)):
            card, layout = self._card()
            label = QLabel(text)
            label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            layout.addWidget(label)
            layout.addWidget(preview, 1)
            workspace.addWidget(card, 1)
        inspector, layout = self._card()
        inspector.setFixedWidth(260 if compact else 280)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        controls = QVBoxLayout(body)
        controls.setContentsMargins(0, 0, 5, 0)
        controls.setSpacing(8)
        controls.addWidget(QLabel("Removal mode"))
        self.mode_group, self.mode_buttons = QButtonGroup(self), []
        for name, description in zip(
            self.removers,
            (
                "Compare both local models",
                "Keep more of the subject",
                "Detailed curls and wispy hair",
            ),
        ):
            button = QRadioButton(name + "\n" + description)
            button.toggled.connect(
                lambda checked, value=name: (
                    self.mode_changed(value) if checked else None
                )
            )
            self.mode_group.addButton(button)
            controls.addWidget(button)
            self.mode_buttons.append(button)
        self.mode_buttons[0].setChecked(True)
        self.remove_button = QPushButton("Remove Background")
        self.remove_button.clicked.connect(self.remove)
        controls.addWidget(self.remove_button)
        self.zoom_slider, self.zoom_label = self._slider(
            controls, "Framing · Zoom", 100, 800
        )
        self.rotation_slider, self.rotation_label = self._slider(
            controls, "Framing · Rotation", -1800, 1800, initial=0
        )
        self.rotation_label.setText("0.0°")
        self.rotation_slider.setToolTip(
            "Straighten tilt: −180° to +180°. Positive angles turn clockwise."
        )
        self.rotation_slider.valueChanged.connect(
            lambda value: self.crop.set_framing(rotation=value / 10)
        )
        self.brightness_slider, self.brightness_label = self._slider(
            controls, "Lighting · Brightness", 25, 200
        )
        self.zoom_slider.valueChanged.connect(
            lambda value: self.crop.set_framing(zoom=value / 100)
        )
        self.brightness_slider.valueChanged.connect(
            lambda value: self.crop.set_framing(brightness=value / 100)
        )
        self.reset_button = QPushButton("Reset Adjustments")
        self.reset_button.clicked.connect(self.crop.reset)
        controls.addWidget(self.reset_button)
        help_text = QLabel(
            "Drag the preview to position.\nRotation: level the eyes with the guide."
            "\nBrightness: 100% is neutral."
        )
        help_text.setWordWrap(True)
        controls.addWidget(help_text)
        controls.addStretch()
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)
        self.save_button = QPushButton("Save 2×2 Photo")
        self.save_button.setProperty("accent", True)
        self.save_button.clicked.connect(self.save)
        layout.addWidget(self.save_button)
        workspace.addWidget(inspector)
        page.addLayout(workspace, 1)
        page.addWidget(
            QLabel("2 × 2 inches · 1200 × 1200 pixels · 600 DPI · White PNG")
        )
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        page.addWidget(self.progress)
        self.status_label = QLabel(
            os.environ.get("PORTRAIT_UPDATE_STATUS", "Ready — offline processing")
        )
        self.status_label.setWordWrap(True)
        page.addWidget(self.status_label)
        self.crop.framing_changed.connect(self._sync_adjustments)

    def _card(self):
        """Create a themed card and its independently managed layout."""
        frame = QFrame()
        frame.setProperty("card", True)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 12, 12, 12)
        return frame, layout

    def _slider(self, layout, title, minimum, maximum, *, initial=100):
        """Create an accessible adjustment slider with a percentage readout."""
        layout.addWidget(QLabel(title))
        row = QHBoxLayout()
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(minimum, maximum)
        slider.setValue(initial)
        slider.setAccessibleName(title)
        label = QLabel("100%")
        label.setMinimumWidth(42)
        row.addWidget(slider, 1)
        row.addWidget(label)
        layout.addLayout(row)
        return slider, label

    def _sync_adjustments(self):
        """Reflect pointer and reset changes without recursively emitting slider events."""
        for slider, value, label in (
            (self.zoom_slider, self.crop.zoom, self.zoom_label),
            (self.brightness_slider, self.crop.brightness, self.brightness_label),
        ):
            slider.blockSignals(True)
            slider.setValue(round(value * 100))
            slider.blockSignals(False)
            label.setText(f"{value:.0%}")
        self.rotation_slider.blockSignals(True)
        self.rotation_slider.setValue(round(self.crop.rotation * 10))
        self.rotation_slider.blockSignals(False)
        self.rotation_label.setText(f"{self.crop.rotation:.1f}°")

    def change_theme(self, name):
        """Change appearance without rebuilding the document or prepared image pixels."""
        if name != self.theme:
            self.theme = name
            apply_theme(name)
            self.theme_buttons[name].setChecked(True)
            save_theme(name, self.preferences_path)

    def _set_busy(self, busy):
        """Keep controls consistent until a background result has been consumed."""
        self.busy = busy
        ready = self.crop.cutout is not None
        for button in (self.open_button, self.paste_button, *self.mode_buttons):
            button.setEnabled(not busy)
        self.remove_button.setEnabled(not busy and self.photo is not None)
        for control in (
            self.edit_button,
            self.auto_skew_button,
            self.save_button,
            self.zoom_slider,
            self.rotation_slider,
            self.brightness_slider,
            self.reset_button,
            self.crop,
        ):
            control.setEnabled(not busy and ready)
        self.progress.setRange(0, 0 if busy else 1)
        self.progress.setValue(0)

    def _work(self, work, accept, description):
        """Run a document operation and reject callbacks for a replaced source."""
        generation = self.generation
        self._set_busy(True)
        self.status_label.setText(description)

        def completed(value, error):
            """Recover controls and consume the current operation on the GUI thread."""
            if generation != self.generation:
                return
            self._set_busy(False)
            if error is not None:
                self.status_label.setText("Operation failed — original photo preserved")
                QMessageBox.warning(self, "IDFrame", str(error))
            else:
                accept(value)

        self.jobs.submit(work, completed)

    def set_photo(self, photo, path=None, description="Photo loaded"):
        """Replace source data and invalidate all previous removal and editing state."""
        self.generation += 1
        self.photo, self.path, self.result = photo, path, None
        self.person_name = ""
        self.before.set_image(photo)
        self.crop.set_image(None)
        self.status_label.setText(description)
        self._set_busy(False)

    def set_cutout(self, cutout):
        """Accept a new removal result with neutral crop and lighting adjustments."""
        self.result = cutout
        self.crop.set_image(cutout)
        self._set_busy(False)

    def open_photo(self):
        """Choose a source and load/orient its pixels outside the GUI thread."""
        if self.busy:
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open portrait",
            "",
            "Photos (*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff);;All files (*)",
        )
        if path:
            self._work(
                lambda: load_photo(path),
                lambda photo: self.set_photo(
                    photo, Path(path), "Opened " + Path(path).name
                ),
                "Loading photo…",
            )

    def paste_photo(self):
        """Load copied image pixels or the first readable local photo URL."""
        if self.busy or QApplication.activeModalWidget() is not None:
            return
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()
        if mime is not None and mime.hasImage():
            snapshot = clipboard.image()
            if not snapshot.isNull():

                def convert_clipboard():
                    """Convert an owned QImage snapshot away from GUI callbacks."""
                    pixels = qt_to_image(snapshot)
                    return Image.alpha_composite(
                        Image.new("RGBA", pixels.size, "white"), pixels
                    ).convert("RGB")

                self._work(
                    convert_clipboard,
                    lambda photo: self.set_photo(
                        photo, None, "Pasted photo from clipboard"
                    ),
                    "Loading clipboard photo…",
                )
                return
        if mime is not None and mime.hasUrls():
            paths = [
                Path(url.toLocalFile()) for url in mime.urls() if url.isLocalFile()
            ]

            def load_first():
                """Skip non-images in a copied file list without altering current data."""
                for path in paths:
                    try:
                        return load_photo(path), path
                    except (OSError, ValueError):
                        continue
                raise ValueError("No supported photo in the clipboard")

            self._work(
                load_first,
                lambda pair: self.set_photo(*pair, "Pasted photo file"),
                "Loading clipboard file…",
            )
            return
        QMessageBox.information(
            self, "Paste photo", "Copy a photo or image file first."
        )

    def mode_changed(self, name):
        """Select a local model and reprocess an existing idle removal result."""
        self.removal_mode = name
        if hasattr(self, "crop") and self.crop.cutout is not None and not self.busy:
            self.remove()

    def process(self, photo, mode="Auto"):
        """Run the selected local model on a worker without accessing Qt controls."""
        return self.removers[mode].remove(photo)

    def remove(self):
        """Submit a single inference job while Qt remains available for painting."""
        if self.busy or self.photo is None:
            return
        self.active_mode = self.removal_mode
        generation, photo, mode = self.generation, self.photo, self.active_mode
        self._work(
            lambda: self.process(photo, mode),
            lambda image: self.accept_removal(generation, image, None),
            "Removing background locally…",
        )

    def accept_removal(self, generation, cutout, error):
        """Apply only a current model result and restore controls after an error."""
        if generation != self.generation:
            return
        self._set_busy(False)
        if error is not None:
            QMessageBox.warning(self, "Could not remove background", str(error))
            return
        self.set_cutout(cutout)
        prefix = ""
        if self.active_mode == "Auto":
            chosen = self.removers["Auto"].last_mode
            prefix = (
                "Auto selected "
                + ("Protect person" if chosen == "protected" else "Fine hair")
                + " · "
            )
        self.status_label.setText(
            prefix + "Ready — Edit artifacts, adjust framing, or save your 2 × 2 photo."
        )

    def auto_skew(self):
        """Estimate absolute rotation off-thread without changing crop or cleanup pixels."""
        if self.busy or self.crop.cutout is None:
            return
        source = self.photo if self.photo is not None else self.crop.cutout

        def apply_angle(angle):
            """Keep uncertain images unchanged and expose the estimate for manual correction."""
            if angle is None:
                self.status_label.setText(
                    "No single usable face found — rotation unchanged. Adjust Rotation manually."
                )
                return
            self.crop.set_framing(rotation=angle)
            self.status_label.setText(
                "Auto-skew applied — check the eye guide and fine-tune Rotation if needed."
            )

        self._work(
            lambda: self.aligner.estimate(source),
            apply_angle,
            "Estimating eye-level rotation…",
        )

    def open_editor(self):
        """Open one separate modal editor to protect document ownership while editing."""
        if self.busy or self.crop.cutout is None:
            return
        from qt_editor import CleanupEditor

        editor = CleanupEditor(self.crop.cutout, self)
        self.editor = editor
        if editor.exec() == editor.DialogCode.Accepted:
            self.apply_edits(editor.edited_image())
        self.editor = None
        editor.deleteLater()

    def apply_edits(self, image):
        """Commit corrected alpha without resetting framing or brightness."""
        self.result = image
        self.crop.set_image(image, reset=False)
        self.status_label.setText("Edits applied — original photo preserved")

    def open_changelog(self):
        """Reuse the local version browser instead of accumulating duplicate windows."""
        if self.changelog_window is None:
            self.changelog_window = changelog_dialog(self, VERSION)
        self.changelog_window.show()
        self.changelog_window.raise_()
        self.changelog_window.activateWindow()

    def save(self):
        """Choose a safe name and export original-resolution pixels on a worker."""
        if self.busy or self.crop.cutout is None:
            return
        name = ask_person_name(self, self.person_name)
        if name is None:
            return
        try:
            filename = portrait_filename(name)
        except ValueError as error:
            QMessageBox.warning(self, "Invalid name", str(error))
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save 2 × 2 portrait",
            filename,
            "PNG image (*.png)",
            options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if not path:
            return
        destination = Path(path)
        if destination.suffix.lower() != ".png":
            destination = destination.with_suffix(".png")
        if self.path is not None and destination.resolve() == Path(self.path).resolve():
            QMessageBox.warning(
                self,
                "Choose another filename",
                "Save a new file to preserve your original photo.",
            )
            return
        self.person_name = name
        cutout, zoom, offset, brightness, rotation = (
            self.crop.cutout,
            self.crop.zoom,
            self.crop.offset,
            self.crop.brightness,
            self.crop.rotation,
        )

        def export():
            """Claim a destination exclusively so another process cannot cause overwrite."""
            image = frame_portrait(
                cutout, zoom, offset, brightness=brightness, rotation=rotation
            )
            while True:
                target = available_photo_path(destination)
                try:
                    save_portrait(image, target, overwrite=False)
                    return target
                except FileExistsError:
                    continue

        self._work(
            export,
            lambda target: self.status_label.setText(
                f"Saved {target.name} — 1200 × 1200 pixels · 600 DPI · White PNG"
            ),
            "Saving portrait…",
        )

    def closeEvent(self, event):
        """Defer shutdown until callbacks drain without blocking or terminating threads."""
        if self.jobs.busy:
            self.status_label.setText("Finishing current work before closing…")
            event.ignore()
            if not self._close_timer_pending:
                self._close_timer_pending = True
                QTimer.singleShot(100, self._retry_close)
            return
        self.jobs.shutdown()
        try:
            from launcher_refresh import request_launcher_refresh

            request_launcher_refresh()
        except Exception:
            import logging

            logging.getLogger(__name__).exception("Launcher refresh deferred")
        event.accept()

    def _retry_close(self):
        """Let queued paints and results execute before retrying graceful window closure."""
        self._close_timer_pending = False
        self.close()


def run():
    """Start the native Qt application and retain the main window for its event loop."""
    application = QApplication.instance() or QApplication(sys.argv)
    application.setStyle("Fusion")
    application.setApplicationName("IDFrame")
    window = PortraitApp()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(run())
