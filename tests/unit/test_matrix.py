"""Cross-generation happy-path smoke — the Viya version matrix (§4).

Runs the same client operations against both the viya4 and viya35 fixture sets
so each generation's response shapes (notably MAS ``output`` vs ``outputs``) are
exercised on every run, from one parametrization.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import responses

from viyapy import FlowBuilder, TermMapping, ViyaClient

BASE = "https://viya.example.com"
TOKEN = "test-token"


@responses.activate
def test_decision_get_across_generations(
    generation: str,
    version_for: Callable[[str], str],
    load_fixture: Callable[[str, str], Any],
) -> None:
    raw = load_fixture(generation, "decision_content.json")
    responses.add(responses.GET, f"{BASE}/decisions/flows/d1", json=raw, status=200)

    client = ViyaClient(BASE, TOKEN, viya_version=version_for(generation), max_retries=0)
    decision = client.decisions.get("d1")

    assert decision.id == "d1"
    assert isinstance(decision.models, tuple)
    assert decision.raw == raw


@responses.activate
def test_mas_execute_across_generations(
    generation: str,
    version_for: Callable[[str], str],
    load_fixture: Callable[[str, str], Any],
) -> None:
    raw = load_fixture(generation, "mas_execute_ok.json")
    url = f"{BASE}/microanalyticScore/modules/m/steps/execute"
    responses.add(responses.POST, url, json=raw, status=200)

    client = ViyaClient(BASE, TOKEN, viya_version=version_for(generation), max_retries=0)
    result = client.mas.execute("m", {"input_string": "x"})

    # Both generations flatten their (differently keyed) output list to a dict.
    assert isinstance(result.outputs, dict)
    assert result.outputs
    assert result.raw == raw


@responses.activate
def test_decision_revisions_across_generations(
    generation: str,
    version_for: Callable[[str], str],
    load_fixture: Callable[[str, str], Any],
) -> None:
    listing = load_fixture(generation, "decision_revisions.json")
    full = load_fixture(generation, "decision_revision.json")
    responses.add(responses.GET, f"{BASE}/decisions/flows/d1/revisions", json=listing, status=200)
    responses.add(responses.GET, f"{BASE}/decisions/flows/d1/revisions/rev", json=full, status=200)

    client = ViyaClient(BASE, TOKEN, viya_version=version_for(generation), max_retries=0)

    revisions = list(client.decisions.revisions("d1"))
    assert revisions and all(r.id for r in revisions)

    decision = client.decisions.get_revision("d1", "rev")
    assert decision.major_revision is not None
    assert decision.raw == full


@responses.activate
def test_decision_code_across_generations(
    generation: str,
    version_for: Callable[[str], str],
    load_fixture_text: Callable[[str, str], str],
) -> None:
    code = load_fixture_text(generation, "decision_code.ds2")
    responses.add(responses.GET, f"{BASE}/decisions/flows/d1/code", body=code, status=200)
    responses.add(
        responses.GET, f"{BASE}/decisions/flows/d1/revisions/rev/code", body=code, status=200
    )

    client = ViyaClient(BASE, TOKEN, viya_version=version_for(generation), max_retries=0)

    # Both generations return the generated DS2 as raw text, verbatim.
    assert client.decisions.get_code("d1") == code
    assert client.decisions.get_revision_code("d1", "rev") == code


@responses.activate
def test_decision_external_artifacts_across_generations(
    generation: str,
    version_for: Callable[[str], str],
    load_fixture: Callable[[str, str], Any],
) -> None:
    raw = load_fixture(generation, "decision_external_artifacts.json")
    responses.add(
        responses.GET, f"{BASE}/decisions/flows/d1/externalArtifacts", json=raw, status=200
    )
    responses.add(
        responses.GET,
        f"{BASE}/decisions/flows/d1/revisions/rev/externalArtifacts",
        json=raw,
        status=200,
    )

    client = ViyaClient(BASE, TOKEN, viya_version=version_for(generation), max_retries=0)

    # Both generations parse the non-paginated collection to a full tuple.
    arts = client.decisions.external_artifacts("d1")
    assert isinstance(arts, tuple)
    assert arts and all(a.name for a in arts)

    rev_arts = client.decisions.revision_external_artifacts("d1", "rev")
    assert [a.name for a in rev_arts] == [a.name for a in arts]


@responses.activate
def test_decision_create_across_generations(
    generation: str,
    version_for: Callable[[str], str],
    load_fixture: Callable[[str, str], Any],
) -> None:
    raw = load_fixture(generation, "decision_created.json")
    responses.add(responses.POST, f"{BASE}/decisions/flows", json=raw, status=201)

    client = ViyaClient(BASE, TOKEN, viya_version=version_for(generation), max_retries=0)

    # Both generations POST the same decision media type and parse the assigned id.
    decision = client.decisions.create("Throwaway Flow", {"steps": []})
    assert decision.id == "new-flow-abc123"
    req = responses.calls[0].request
    assert req.headers["Content-Type"] == "application/vnd.sas.decision+json"
    assert req.headers["Accept"] == "application/vnd.sas.decision+json"


@responses.activate
def test_decision_create_from_builder_across_generations(
    generation: str,
    version_for: Callable[[str], str],
    load_fixture: Callable[[str, str], Any],
) -> None:
    raw = load_fixture(generation, "decision_created.json")
    responses.add(responses.POST, f"{BASE}/decisions/flows", json=raw, status=201)

    client = ViyaClient(BASE, TOKEN, viya_version=version_for(generation), max_retries=0)

    # The typed builder is generation-agnostic: the same flow body is POSTed for
    # both generations (the create body itself carries no version-specific shape).
    flow = FlowBuilder().model("m-1", mappings=[TermMapping.input("DEBTINC")])
    client.decisions.create("Throwaway Flow", flow)
    sent = json.loads(responses.calls[0].request.body)
    assert sent["flow"] == flow.build()


@responses.activate
def test_decision_update_delete_across_generations(
    generation: str,
    version_for: Callable[[str], str],
    load_fixture: Callable[[str, str], Any],
) -> None:
    raw = load_fixture(generation, "decision_created.json")
    url = f"{BASE}/decisions/flows/d1"
    responses.add(responses.GET, url, json=raw, status=200, headers={"ETag": '"e1"'})
    responses.add(responses.PUT, url, json=raw, status=200)
    responses.add(responses.DELETE, url, status=204)

    client = ViyaClient(BASE, TOKEN, viya_version=version_for(generation), max_retries=0)

    # Update reads the ETag then PUTs it back as If-Match, identically per generation.
    client.decisions.update("d1", description="changed")
    put_call = responses.calls[1].request
    assert put_call.method == "PUT"
    assert put_call.headers["If-Match"] == '"e1"'

    # Delete tolerates the empty 204 body.
    assert client.decisions.delete("d1") is None
