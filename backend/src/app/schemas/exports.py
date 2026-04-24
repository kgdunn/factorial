"""Pydantic schemas and enums for the export endpoints."""

from __future__ import annotations

from enum import StrEnum


class ExportFormat(StrEnum):
    """Formats supported by ``GET /experiments/{id}/export``.

    ``pdf`` / ``xlsx`` / ``csv`` / ``md`` render static report artifacts.
    ``py`` / ``ipynb`` / ``md_code`` render runnable code that reproduces
    the analysis by replaying the captured ``process_improve`` tool
    calls.  ``zip`` delivers the full reproducible bundle (all three
    code formats plus ``data.xlsx``, ``README.md`` and a pinned
    ``requirements.txt``) — the form users download when they want to
    re-run the analysis locally without re-spending agent tokens.
    """

    pdf = "pdf"
    xlsx = "xlsx"
    csv = "csv"
    md = "md"
    py = "py"
    ipynb = "ipynb"
    # ``md_code`` and ``md`` both use a ``.md`` extension because they
    # are both markdown; they differ in content (static report vs.
    # literate code walkthrough).  The format enum keeps them distinct.
    md_code = "md_code"
    zip = "zip"


EXPORT_MEDIA_TYPES: dict[ExportFormat, str] = {
    ExportFormat.pdf: "application/pdf",
    ExportFormat.xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ExportFormat.csv: "text/csv",
    ExportFormat.md: "text/markdown",
    ExportFormat.py: "text/x-python",
    ExportFormat.ipynb: "application/x-ipynb+json",
    ExportFormat.md_code: "text/markdown",
    ExportFormat.zip: "application/zip",
}


EXPORT_EXTENSIONS: dict[ExportFormat, str] = {
    ExportFormat.pdf: "pdf",
    ExportFormat.xlsx: "xlsx",
    ExportFormat.csv: "csv",
    ExportFormat.md: "md",
    ExportFormat.py: "py",
    ExportFormat.ipynb: "ipynb",
    ExportFormat.md_code: "md",
    ExportFormat.zip: "zip",
}
