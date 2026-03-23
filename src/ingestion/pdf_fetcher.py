"""Download or read PDFs, extract text with PyPDF2, structure with OpenAI."""

from __future__ import annotations

import io
import json
import os
import re
from typing import Any, Mapping

import requests
from PyPDF2 import PdfReader

from .base import DataFetcher
from .models import FetchResult, SourceConfig


class PDFFetcher(DataFetcher):
    """
    Fetches a PDF from `source_url` (or uses local path in `extra["pdf_path"]`),
    extracts text with PyPDF2, then asks OpenAI to pull the target metric.
    """

    def __init__(
        self,
        source: SourceConfig,
        defaults: Mapping[str, Any] | None = None,
        *,
        session_headers: Mapping[str, str] | None = None,
        openai_model: str | None = None,
    ) -> None:
        super().__init__(source, defaults, session_headers=session_headers)
        self.openai_model = openai_model or os.environ.get(
            "OPENAI_MODEL", "gpt-4o-mini"
        )

    def _pdf_bytes(self) -> bytes:
        extra = self.source.extra or {}
        local = extra.get("pdf_path")
        if local:
            with open(local, "rb") as f:
                return f.read()
        r = requests.get(
            self.source.source_url,
            headers=self._default_headers(),
            timeout=self._timeout(),
        )
        r.raise_for_status()
        return r.content

    def _extract_text(self, pdf_bytes: bytes) -> str:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        parts: list[str] = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
        return "\n".join(parts)

    def _openai_extract(self, pdf_text: str) -> dict[str, Any]:
        from openai import OpenAI

        client = OpenAI()
        metric = self.source.target_metric
        prompt = (
            "You are extracting structured data for a regional scorecard.\n"
            f"Target metric id/name: {metric!r}\n"
            "From the following PDF text, find the best numeric value(s) or table cells "
            "that correspond to this metric. Respond with a single JSON object only, "
            'keys: "value" (number or string), "unit" (string or null), '
            '"evidence" (short quote from the text), "confidence" (0-1).\n\n'
            "--- PDF TEXT ---\n"
            f"{pdf_text[:120000]}"
        )
        resp = client.chat.completions.create(
            model=self.openai_model,
            messages=[
                {"role": "system", "content": "Reply with valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )
        raw = (resp.choices[0].message.content or "").strip()
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            raise ValueError(f"OpenAI did not return JSON: {raw[:500]}")
        return json.loads(m.group())

    def fetch(self) -> FetchResult:
        try:
            pdf_bytes = self._pdf_bytes()
            text = self._extract_text(pdf_bytes)
            if not text.strip():
                return FetchResult(
                    success=False,
                    target_metric=self.source.target_metric,
                    source_id=self.source.id,
                    error="No extractable text in PDF",
                )
            structured = self._openai_extract(text)
        except Exception as e:
            return FetchResult(
                success=False,
                target_metric=self.source.target_metric,
                source_id=self.source.id,
                error=str(e),
            )

        return FetchResult(
            success=True,
            target_metric=self.source.target_metric,
            source_id=self.source.id,
            data=structured,
            raw=text[:8000],
            source_used="openai_extraction",
        )
