"""Native Qt name and changelog dialogs for the portrait application."""

import json
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QDialogButtonBox,
    QListWidget,
    QTextBrowser,
)

from photo_naming import portrait_filename


def ask_person_name(parent, initial="", *, size_key="2x2"):
    """Ask for a validated person name with a live export-filename preview."""
    dialog = QDialog(parent)
    dialog.setWindowTitle("Name this portrait")
    dialog.setMinimumWidth(420)
    layout = QVBoxLayout(dialog)
    layout.addWidget(QLabel("Person's name"))
    entry = QLineEdit(initial)
    entry.setPlaceholderText("Example: Juan Dela Cruz")
    layout.addWidget(entry)
    preview = QLabel()
    preview.setWordWrap(True)
    layout.addWidget(preview)
    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    def validate():
        """Preview the safe filename and prevent accepting an invalid name."""
        try:
            filename = portrait_filename(entry.text(), size_key)
        except ValueError as error:
            preview.setText(str(error))
            buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        else:
            preview.setText("Filename: " + filename)
            buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)

    entry.textChanged.connect(validate)
    validate()
    entry.selectAll()
    entry.setFocus()
    return (
        entry.text().strip() if dialog.exec() == QDialog.DialogCode.Accepted else None
    )


def changelog_dialog(parent, installed_version):
    """Construct a local version-indexed notes browser without network access."""
    dialog = QDialog(parent)
    dialog.setWindowTitle("IDFrame — Changelog")
    dialog.resize(720, 460)
    layout = QVBoxLayout(dialog)
    layout.addWidget(QLabel(f"Changelog · Installed v{installed_version}"))
    body = QHBoxLayout()
    versions, notes = QListWidget(), QTextBrowser()
    versions.setMaximumWidth(150)
    body.addWidget(versions)
    body.addWidget(notes, 1)
    layout.addLayout(body)
    path = Path(__file__).resolve().parent / "assets/changelog.json"
    releases = sorted(
        json.loads(path.read_text(encoding="utf-8")),
        key=lambda item: tuple(int(part) for part in item["version"].split(".")),
        reverse=True,
    )
    for release in releases:
        versions.addItem("v" + release["version"])

    def select_release(index):
        """Show selected release notes as plain text rather than interpreting markup."""
        if 0 <= index < len(releases):
            release = releases[index]
            notes.setPlainText(
                "Version "
                + release["version"]
                + "\n\n"
                + "\n\n".join("• " + text for text in release["changes"])
            )

    versions.currentRowChanged.connect(select_release)
    versions.setCurrentRow(
        next(
            (
                index
                for index, release in enumerate(releases)
                if release["version"] == installed_version
            ),
            0,
        )
    )
    return dialog
