"""Pydantic schemas and enums for the export endpoints."""

from __future__ import annotations

from enum import StrEnum


class ExportFormat(StrEnum):
    """Formats supported by ``GET /experiments/{id}/export``.

    ``pdf`` / ``xlsx`` / ``csv`` / ``md`` render static report artifacts.
    ``py`` renders a runnable Python script that reproduces the analysis
    by replaying the captured ``process_improve`` tool calls — the first
    step of the reproducible-code-export work tracked in ``TODO.md``.
    """

    pdf = "pdf"
    xlsx = "xlsx"
    csv = "csv"
    md = "md"
    py = "py"


EXPORT_MEDIA_TYPES: dict[ExportFormat, str] = {
    ExportFormat.pdf: "application/pdf",
    ExportFormat.xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ExportFormat.csv: "text/csv",
    ExportFormat.md: "text/markdown",
    ExportFormat.py: "text/x-python",
}


EXPORT_EXTENSIONS: dict[ExportFormat, str] = {
    ExportFormat.pdf: "pdf",
    ExportFormat.xlsx: "xlsx",
    ExportFormat.csv: "csv",
    ExportFormat.md: "md",
    ExportFormat.py: "py",
}
