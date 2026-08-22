"""Minimal HTML table extractor (stdlib only)."""

from __future__ import annotations

import re
from html.parser import HTMLParser


class TableExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[dict] = []
        self._table: dict | None = None
        self._row: list[str] | None = None
        self._in_cell = False
        self._cell: list[str] = []
        self._in_heading = False
        self._heading: list[str] = []
        self._last_heading = ""
        self._ignore = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._ignore = True
            return
        if self._ignore:
            return
        if tag in {"h1", "h2", "h3", "h4", "h5"}:
            self._in_heading = True
            self._heading = []
        elif tag == "table":
            self._table = {"heading": self._last_heading, "rows": []}
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._in_cell = True
            self._cell = []
        elif tag == "br" and self._in_cell:
            self._cell.append(" ")
        elif tag == "br" and self._in_heading:
            self._heading.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self._ignore = False
            return
        if self._ignore:
            return
        if tag in {"h1", "h2", "h3", "h4", "h5"} and self._in_heading:
            text = _clean("".join(self._heading))
            if text:
                self._last_heading = text
            self._in_heading = False
        elif tag in {"td", "th"} and self._in_cell:
            assert self._row is not None
            self._row.append(_clean("".join(self._cell)))
            self._in_cell = False
        elif tag == "tr" and self._row is not None:
            if any(self._row) and self._table is not None:
                self._table["rows"].append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            if self._table["rows"]:
                self.tables.append(self._table)
            self._table = None

    def handle_data(self, data: str) -> None:
        if self._ignore:
            return
        if self._in_cell:
            self._cell.append(data)
        elif self._in_heading:
            self._heading.append(data)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_tables(html: str) -> list[dict]:
    parser = TableExtractor()
    parser.feed(html)
    parser.close()
    return parser.tables
