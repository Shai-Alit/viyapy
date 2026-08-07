"""Unit tests for the reusable collection pagination iterator."""

from __future__ import annotations

import responses

from viyapy._http import HttpClient
from viyapy._pagination import iter_collection

BASE = "https://viya.example.com"


def make_http() -> HttpClient:
    return HttpClient(BASE, "tok", max_retries=0)


@responses.activate
def test_single_page_yields_items_and_stops() -> None:
    responses.add(
        responses.GET,
        f"{BASE}/things",
        json={"items": [{"id": "a"}, {"id": "b"}], "links": []},
        status=200,
    )
    items = list(iter_collection(make_http(), "/things"))
    assert [i["id"] for i in items] == ["a", "b"]
    assert len(responses.calls) == 1


@responses.activate
def test_follows_next_link_across_pages() -> None:
    responses.add(
        responses.GET,
        f"{BASE}/things",
        json={
            "items": [{"id": "a"}],
            "links": [{"rel": "next", "href": "/things?start=1&limit=1"}],
        },
        status=200,
    )
    responses.add(
        responses.GET,
        f"{BASE}/things?start=1&limit=1",
        json={"items": [{"id": "b"}], "links": [{"rel": "prev", "href": "/things"}]},
        status=200,
        match_querystring=True,
    )
    items = list(iter_collection(make_http(), "/things"))
    assert [i["id"] for i in items] == ["a", "b"]
    assert len(responses.calls) == 2


@responses.activate
def test_absolute_next_href_is_normalized() -> None:
    responses.add(
        responses.GET,
        f"{BASE}/things",
        json={
            "items": [{"id": "a"}],
            "links": [{"rel": "next", "href": f"{BASE}/things?start=1"}],
        },
        status=200,
    )
    responses.add(
        responses.GET,
        f"{BASE}/things?start=1",
        json={"items": [{"id": "b"}], "links": []},
        status=200,
        match_querystring=True,
    )
    items = list(iter_collection(make_http(), "/things"))
    assert [i["id"] for i in items] == ["a", "b"]


@responses.activate
def test_self_referential_next_link_terminates() -> None:
    # A server that keeps returning a next link pointing at the same page must
    # not loop forever.
    responses.add(
        responses.GET,
        f"{BASE}/things",
        json={"items": [{"id": "a"}], "links": [{"rel": "next", "href": "/things"}]},
        status=200,
    )
    items = list(iter_collection(make_http(), "/things"))
    assert [i["id"] for i in items] == ["a"]
    assert len(responses.calls) == 1


@responses.activate
def test_non_mapping_items_are_skipped() -> None:
    responses.add(
        responses.GET,
        f"{BASE}/things",
        json={"items": [{"id": "a"}, "junk", 5], "links": []},
        status=200,
    )
    items = list(iter_collection(make_http(), "/things"))
    assert [i["id"] for i in items] == ["a"]


@responses.activate
def test_first_page_params_are_sent() -> None:
    responses.add(
        responses.GET,
        f"{BASE}/things?limit=100",
        json={"items": [], "links": []},
        status=200,
        match_querystring=True,
    )
    list(iter_collection(make_http(), "/things", params={"limit": 100}))
    assert responses.calls[0].request.url.endswith("limit=100")


@responses.activate
def test_missing_or_non_list_items_yields_nothing() -> None:
    # A page whose ``items`` is absent (or not a list) is tolerated: no items,
    # and with no next link, iteration ends cleanly.
    responses.add(
        responses.GET,
        f"{BASE}/things",
        json={"items": {"not": "a list"}},
        status=200,
    )
    assert list(iter_collection(make_http(), "/things")) == []
    assert len(responses.calls) == 1


@responses.activate
def test_non_list_links_terminates() -> None:
    # ``links`` present but not a list must be treated as "no next link".
    responses.add(
        responses.GET,
        f"{BASE}/things",
        json={"items": [{"id": "a"}], "links": {"rel": "next"}},
        status=200,
    )
    assert [i["id"] for i in iter_collection(make_http(), "/things")] == ["a"]
    assert len(responses.calls) == 1


@responses.activate
def test_next_link_with_empty_href_terminates() -> None:
    # A ``rel: next`` entry carrying no usable href/uri is skipped, not chased.
    responses.add(
        responses.GET,
        f"{BASE}/things",
        json={"items": [{"id": "a"}], "links": [{"rel": "next", "href": ""}]},
        status=200,
    )
    assert [i["id"] for i in iter_collection(make_http(), "/things")] == ["a"]
    assert len(responses.calls) == 1


@responses.activate
def test_absolute_next_href_with_foreign_host_is_reduced_to_path() -> None:
    # An absolute next URL on a different host than base_url falls back to
    # urlparse, keeping only path + query so the client resolves it locally.
    responses.add(
        responses.GET,
        f"{BASE}/things",
        json={
            "items": [{"id": "a"}],
            "links": [{"rel": "next", "href": "https://other.example.net/things?start=1"}],
        },
        status=200,
    )
    responses.add(
        responses.GET,
        f"{BASE}/things?start=1",
        json={"items": [{"id": "b"}], "links": []},
        status=200,
        match_querystring=True,
    )
    items = list(iter_collection(make_http(), "/things"))
    assert [i["id"] for i in items] == ["a", "b"]
