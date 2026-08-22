"""Merge poe-ninja-translator names into names_zh.json and scrape poedb pairs."""

from __future__ import annotations

import json
import re
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

UA = {
    "User-Agent": "PoELookupTool/1.0 (Windows desktop; personal local app)",
    "Accept-Language": "zh-TW,en;q=0.8",
}
NINJA_JSON = "https://raw.githubusercontent.com/yuh926323/poe-ninja-translator/main/json/language_zh_tw.json"
PAREN = re.compile(r"\s*\([^()]*\)\s*$")
CJK = re.compile(r"[\u4e00-\u9fff]")
POEDB_PAGES = [
    "Divination_Cards",
    "Essence",
    "Scarab",
    "Fossil",
    "Oil",
    "Delirium_Orb",
    "Incubator",
    "Resonator",
    "Omen",
    "Tattoo",
    "Invitation",
]


class LinkParser(HTMLParser):
    def __init__(self, prefix: str) -> None:
        super().__init__(convert_charrefs=True)
        self.prefix = prefix
        self.links: dict[str, str] = {}
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href") or ""
        if self.prefix in href:
            slug = href.rsplit("/", 1)[-1]
            if slug and slug not in {self.prefix.strip("/"), "Items"}:
                self._href = slug
                self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            text = re.sub(r"\s+", " ", "".join(self._text)).strip()
            if text:
                self.links.setdefault(self._href, text)
            self._href = None


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read().decode("utf-8", "replace")


def flatten_translator(node, out: dict[str, str]) -> None:
    if isinstance(node, dict):
        name = node.get("name")
        zh = node.get("name_zh_tw")
        if isinstance(name, str) and isinstance(zh, str):
            cleaned = PAREN.sub("", zh).strip()
            if name and cleaned and cleaned != name and CJK.search(cleaned):
                out.setdefault(name, cleaned)
        for value in node.values():
            flatten_translator(value, out)
    elif isinstance(node, list):
        for item in node:
            flatten_translator(item, out)


def poedb_pairs(page: str) -> dict[str, str]:
    tw_html = fetch(f"https://poedb.tw/tw/{page}")
    us_html = fetch(f"https://poedb.tw/us/{page}")
    tw = LinkParser("/tw/")
    us = LinkParser("/us/")
    tw.feed(tw_html)
    us.feed(us_html)
    mapping: dict[str, str] = {}
    for slug, english in us.links.items():
        chinese = tw.links.get(slug)
        if not chinese or not CJK.search(chinese) or chinese == english:
            continue
        mapping.setdefault(english, chinese)
    return mapping


def main() -> None:
    out_path = Path("poe_affix_data/names_zh.json")
    mapping: dict[str, str] = {}
    if out_path.exists():
        mapping.update(json.loads(out_path.read_text(encoding="utf-8")))
        print("existing", len(mapping))

    print("download ninja translator json")
    translator = json.loads(fetch(NINJA_JSON))
    before = len(mapping)
    flatten_translator(translator, mapping)
    print("after translator", len(mapping), "added", len(mapping) - before)

    for page in POEDB_PAGES:
        before = len(mapping)
        try:
            pairs = poedb_pairs(page)
        except Exception as error:
            print("poedb fail", page, error)
            continue
        for english, chinese in pairs.items():
            mapping.setdefault(english, chinese)
        print("poedb", page, "pairs", len(pairs), "added", len(mapping) - before)

    out_path.write_text(json.dumps(mapping, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("wrote", out_path, "entries", len(mapping), "bytes", out_path.stat().st_size)


if __name__ == "__main__":
    main()
