"""Pydantic schemas and enums for the export endpoints."""

from __future__ import annotations

from enum import StrEnum


class ExportFormat(StrEnum):
    """Formats supported by ``GET /experiments/{id}/export``."""

    pdf = "pdf"
    xlsx = "xlsx"
    csv = "csv"
    md = "md"


EXPORT_MEDIA_TYPES: dict[ExportFormat, str] = {
    ExportFormat.pdf: "application/pdf",
    ExportFormat.xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ExportFormat.csv: "text/csv",
    ExportFormat.md: "text/markdown",
}


EXPORT_EXTENSIONS: dict[ExportFormat, str] = {
    ExportFormat.pdf: "pdf",
    ExportFormat.xlsx: "xlsx",
    ExportFormat.csv: "csv",
    ExportFormat.md: "md",
}
