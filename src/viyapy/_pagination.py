"""Iterate paginated SAS Viya collection responses.

SAS Viya list endpoints return a ``application/vnd.sas.collection+json``
representation: the current page's items under ``items`` and HATEOAS ``links``
carrying a ``rel: "next"`` pointer to the following page. :func:`iter_collection`
walks those pages lazily, following ``next`` links until none remains, and yields
each raw item mapping.

This is a shared foundation: every ``list``-style operation added in later phases
(decisions, rulesets, publishing destinations, CAS tables) reuses it, so
pagination is implemented and tested once.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

if TYPE_CHECKING:
    from ._http import HttpClient

COLLECTION_MEDIA_TYPE = "application/vnd.sas.collection+json"


def iter_collection(
    http: HttpClient,
    path: str,
    *,
    accept: str = COLLECTION_MEDIA_TYPE,
    params: Mapping[str, Any] | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield each item of a paginated SAS collection, following ``next`` links.

    Args:
        http: The HTTP client used to fetch each page.
        path: Path (relative to the client's ``base_url``) of the first page.
        accept: ``Accept`` header sent for each page request.
        params: Query parameters for the first page only (e.g. ``{"limit": 100}``);
            subsequent pages use the server-provided ``next`` link, which already
            carries its own query string.

    Yields:
        Each item mapping from every page, in server order.

    Raises:
        ViyaError: Propagated from the underlying page requests.
    """
    next_path: str | None = path
    next_params = dict(params) if params else None
    # A misbehaving server could return a ``next`` link identical to the current
    # page; tracking visited targets guarantees termination.
    visited: set[str] = set()

    while next_path is not None and next_path not in visited:
        visited.add(next_path)
        page = http.request_json("GET", next_path, accept=accept, params=next_params)
        items = page.get("items")
        if isinstance(items, list):
            for item in items:
                if isinstance(item, Mapping):
                    yield dict(item)
        next_path = _next_link(page, http.base_url)
        next_params = None  # the next link already encodes its query parameters


def _next_link(page: Mapping[str, Any], base_url: str) -> str | None:
    """Return the ``rel: "next"`` link target as a client-relative path, if any."""
    links = page.get("links")
    if not isinstance(links, list):
        return None
    for link in links:
        if isinstance(link, Mapping) and link.get("rel") == "next":
            href = link.get("href") or link.get("uri")
            if href:
                return _relative(str(href), base_url)
    return None


def _relative(href: str, base_url: str) -> str:
    """Reduce a link href to a path (+query) the HTTP client can resolve.

    SAS links are usually server-relative (``/microanalyticScore/modules?...``),
    but tolerate an absolute URL by stripping the scheme/host.
    """
    if href.startswith(base_url):
        return href[len(base_url) :] or "/"
    parsed = urlparse(href)
    if parsed.scheme and parsed.netloc:
        return parsed.path + (f"?{parsed.query}" if parsed.query else "")
    return href
