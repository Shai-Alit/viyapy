"""Unit tests for ViyaClient construction and wiring."""

from __future__ import annotations

from unittest import mock

import requests

from viyapy import ViyaClient
from viyapy.decisions import DecisionsAPI
from viyapy.dialects import Viya4Dialect, Viya35Dialect
from viyapy.mas import MASClient

BASE = "https://viya.example.com"


def test_defaults_to_viya4() -> None:
    client = ViyaClient(BASE, "tok", session=mock.Mock(spec=requests.Session))
    assert isinstance(client.dialect, Viya4Dialect)
    assert isinstance(client.decisions, DecisionsAPI)
    assert isinstance(client.mas, MASClient)


def test_version_selects_dialect() -> None:
    client = ViyaClient(BASE, "tok", viya_version="3.5", session=mock.Mock(spec=requests.Session))
    assert isinstance(client.dialect, Viya35Dialect)


def test_base_url_property_normalized() -> None:
    client = ViyaClient(BASE + "/", "tok", session=mock.Mock(spec=requests.Session))
    assert client.base_url == BASE


def test_repr_has_no_token() -> None:
    client = ViyaClient(BASE, "secret-token", session=mock.Mock(spec=requests.Session))
    text = repr(client)
    assert "secret-token" not in text
    assert "viya4" in text


def test_context_manager_closes_session() -> None:
    session = mock.Mock(spec=requests.Session)
    with ViyaClient(BASE, "tok", session=session) as client:
        assert isinstance(client, ViyaClient)
    session.close.assert_called_once()
