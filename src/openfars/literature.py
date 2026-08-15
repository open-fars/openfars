from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Mapping, Optional

import requests


@dataclass(frozen=True)
class Paper:
    id: str
    title: str
    year: Optional[int]
    authors: List[str]
    venue: str
    doi: Optional[str]
    url: str
    abstract: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class LiteratureClient:
    """Small evidence adapter; OpenAlex is keyless and returns stable work IDs."""

    def __init__(self, timeout: int = 15, session: Optional[requests.Session] = None):
        self.timeout = timeout
        self.session = session or requests.Session()

    def search(self, query: str, limit: int = 8) -> List[Paper]:
        if not query.strip():
            return []
        response = self.session.get(
            "https://api.openalex.org/works",
            params={
                "search": query,
                "per-page": min(max(limit, 1), 50),
                "select": (
                    "id,display_name,publication_year,authorships,primary_location,"
                    "doi,open_access,abstract_inverted_index"
                ),
            },
            headers={"User-Agent": "OpenFARS/0.2 (https://github.com/open-fars/openfars)"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        results = response.json().get("results", [])
        return [self._paper(item) for item in results if item.get("display_name")]

    @staticmethod
    def _paper(item: Mapping[str, Any]) -> Paper:
        authors = [
            str(entry.get("author", {}).get("display_name"))
            for entry in item.get("authorships", [])[:8]
            if entry.get("author", {}).get("display_name")
        ]
        location = item.get("primary_location") or {}
        source = location.get("source") or {}
        url = location.get("landing_page_url") or item.get("doi") or item.get("id", "")
        return Paper(
            id=str(item.get("id", "")).rsplit("/", 1)[-1],
            title=str(item.get("display_name", "")),
            year=item.get("publication_year"),
            authors=authors,
            venue=str(source.get("display_name") or ""),
            doi=item.get("doi"),
            url=str(url),
            abstract=_rebuild_abstract(item.get("abstract_inverted_index")),
        )


def _rebuild_abstract(index: Any) -> str:
    if not isinstance(index, dict):
        return ""
    positioned: List[tuple[int, str]] = []
    for token, positions in index.items():
        if not isinstance(positions, list):
            continue
        positioned.extend((int(position), str(token)) for position in positions)
    return re.sub(r"\s+", " ", " ".join(token for _, token in sorted(positioned)))
