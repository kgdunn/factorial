"""Render an ECharts option dict to a PNG byte string.

WeasyPrint (our PDF engine) does not run JavaScript, so ECharts plots
cannot render inside the PDF on their own.  This service uses Playwright
to launch a headless Chromium context, inject the ECharts library and
the option dict, and screenshot the resulting canvas.

The browser is expensive to start, so we keep a single async singleton
per process.  Failures fall back to a minimal SVG placeholder so PDF
export never hard-fails on environments without Playwright/Chromium.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


_HTML_TEMPLATE = """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    html, body {{ margin: 0; padding: 0; background: white; }}
    #chart {{ width: {width}px; height: {height}px; }}
  </style>
</head>
<body>
  <div id="chart"></div>
  <script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/echarts-gl@2/dist/echarts-gl.min.js"></script>
  <script>
    const option = {option_json};
    const chart = echarts.init(document.getElementById('chart'));
    chart.setOption(option);
    // Expose readiness so the Python side can await rendering completion.
    window.__chartReady = true;
  </script>
</body>
</html>
"""


_FALLBACK_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 300">'
    '<rect width="600" height="300" fill="#f5f5f5"/>'
    '<text x="300" y="150" text-anchor="middle" fill="#666" '
    'font-family="sans-serif" font-size="16">'
    "Interactive chart — view at the share link"
    "</text></svg>"
).encode()


class _BrowserSingleton:
    """Lazy per-process Playwright browser."""

    _instance: _BrowserSingleton | None = None
    _lock = asyncio.Lock()

    def __init__(self) -> None:
        self._playwright: Any | None = None
        self._browser: Any | None = None

    @classmethod
    async def get(cls) -> _BrowserSingleton:
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
                await cls._instance._start()
            return cls._instance

    async def _start(self) -> None:
        from playwright.async_api import async_playwright  # noqa: PLC0415

        self._playwright = await async_playwright().start()
        launch_kwargs: dict[str, Any] = {"args": ["--no-sandbox"]}
        if settings.exports_chromium_path:
            launch_kwargs["executable_path"] = settings.exports_chromium_path
        self._browser = await self._playwright.chromium.launch(**launch_kwargs)

    async def new_page(self, *, width: int, height: int) -> Any:
        if self._browser is None:
            raise RuntimeError("Browser not initialised")
        context = await self._browser.new_context(viewport={"width": width, "height": height})
        return await context.new_page(), context


async def render_echarts_png(
    option: dict[str, Any],
    *,
    width: int = 800,
    height: int = 500,
    timeout_ms: int = 8000,
) -> bytes:
    """Render an ECharts option dict to PNG bytes.

    Falls back to an SVG placeholder (still bytes) if Playwright or
    Chromium is unavailable — the PDF will embed the SVG as an image
    with the same framing so the report stays usable in minimal
    deployments.
    """
    try:
        browser = await _BrowserSingleton.get()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Playwright unavailable (%s); using placeholder", exc)
        return _FALLBACK_SVG

    page = None
    context = None
    try:
        page, context = await browser.new_page(width=width, height=height)
        html = _HTML_TEMPLATE.format(
            width=width,
            height=height,
            option_json=json.dumps(option),
        )
        await page.set_content(html, wait_until="networkidle", timeout=timeout_ms)
        await page.wait_for_function("window.__chartReady === true", timeout=timeout_ms)
        # Give ECharts one animation frame to finish drawing.
        await page.wait_for_timeout(300)
        element = await page.query_selector("#chart")
        if element is None:
            return _FALLBACK_SVG
        return await element.screenshot(type="png")
    except Exception as exc:  # noqa: BLE001
        logger.warning("ECharts render failed (%s); using placeholder", exc)
        return _FALLBACK_SVG
    finally:
        if page is not None:
            await page.close()
        if context is not None:
            await context.close()
