"""Operations on SAS Intelligent Decisioning decision flows."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

from ._http import HttpClient
from ._pagination import DEFAULT_PAGE_SIZE, iter_collection
from ._revisions import RevisionsMixin
from ._validation import require_identifier, require_non_empty_str, require_positive_int
from .dialects.base import Dialect
from .exceptions import ViyaConfigError, ViyaResponseError
from .models import Decision, DecisionSummary, ExternalArtifact, ModelStep


class DecisionsAPI(RevisionsMixin[Decision]):
    """Decision-flow operations, accessed via ``ViyaClient.decisions``.

    Beyond :meth:`list`/:meth:`get`, this exposes a decision flow's revision
    history via :meth:`revisions` and :meth:`get_revision` (inherited from
    :class:`~viyapy._revisions.RevisionsMixin`). A plain :meth:`get` returns the
    *current* revision; :meth:`get_revision` returns the flow's content at a
    specific historical revision — both as a :class:`~viyapy.models.Decision`.
    """

    def __init__(self, http: HttpClient, dialect: Dialect) -> None:
        self._http = http
        self._dialect = dialect

    def list(self, *, page_size: int = DEFAULT_PAGE_SIZE) -> Iterator[DecisionSummary]:
        """Iterate the decision flows on the deployment, one per yielded item.

        Pages are fetched lazily as the iterator is consumed (following the
        collection's ``next`` links), so a large deployment is streamed rather
        than buffered. ``page_size`` is validated eagerly, when this method is
        called, so a bad value fails fast at the call site rather than on the
        first iteration.

        Each yielded :class:`DecisionSummary` is the lightweight collection
        representation; call :meth:`get` with its ``id`` to load the full flow.

        Args:
            page_size: Number of flows requested per page. Larger pages mean
                fewer round trips; the server may cap the effective size.

        Returns:
            An iterator over each :class:`DecisionSummary`, in server order.

        Raises:
            ViyaConfigError: ``page_size`` is not a positive integer.
            ViyaError: On any request failure while paging.
        """
        # Validate eagerly here (not in the generator below): a generator
        # function defers its whole body until first iteration, which would
        # postpone this check and defeat the fail-fast contract.
        require_positive_int(page_size, "page_size")
        return self._iter_flows(page_size)

    def _iter_flows(self, page_size: int) -> Iterator[DecisionSummary]:
        """Lazily page through the decision-flows collection (see :meth:`list`)."""
        items = iter_collection(
            self._http,
            self._dialect.decisions_flows_path(),
            params={"limit": page_size},
        )
        for item in items:
            yield self._dialect.parse_decision_summary(item)

    def get(self, decision_id: str) -> Decision:
        """Fetch a decision flow's content.

        Args:
            decision_id: The decision id.

        Returns:
            The parsed :class:`Decision`.

        Raises:
            ViyaConfigError: ``decision_id`` is empty or not a string.
            ViyaNotFoundError: No decision with that id exists.
            ViyaError: On any other failure.
        """
        decision_id = require_identifier(decision_id, "decision_id")
        raw = self._http.request_json(
            "GET",
            self._dialect.decision_path(decision_id),
            accept=self._dialect.decision_media_type,
        )
        return self._dialect.parse_decision(decision_id, raw)

    def list_models(self, decision_id: str) -> tuple[ModelStep, ...]:
        """Return the model steps contained in a decision flow.

        Convenience wrapper over :meth:`get`; it issues a fresh request each
        call and does not cache. Call :meth:`get` once and reuse the returned
        :class:`Decision` if you need the flow and its models together.
        """
        return self.get(decision_id).models

    def create(
        self,
        name: str,
        flow: Mapping[str, Any],
        *,
        description: str | None = None,
        signature: Any | None = None,
        properties: Any | None = None,
        timeout: float | tuple[float, float] | None = None,
    ) -> Decision:
        """Create a new decision flow.

        Posts a decision-flow definition to the deployment and returns the
        server's representation of the freshly created flow — with the id,
        revision numbers (``majorRevision``/``minorRevision``), and audit fields
        the server assigns.

        For phase 5.4a the flow graph is passed through as a **raw dict** (the
        ``flow`` argument) rather than assembled from a typed builder; an empty
        ``{"steps": []}`` is a valid flow. ``signature`` and ``properties`` are
        likewise forwarded verbatim when given.

        Args:
            name: The flow's display name. Must be a non-empty string.
            flow: The flow graph as a mapping (e.g. ``{"steps": [...]}``), sent
                verbatim. May contain an empty ``steps`` list.
            description: Optional human-readable description.
            signature: Optional decision signature (variables), forwarded as-is.
            properties: Optional decision properties, forwarded as-is.
            timeout: Optional per-call timeout override.

        Returns:
            The parsed :class:`Decision` for the created flow.

        Raises:
            ViyaConfigError: ``name`` is empty or not a string, or ``flow`` is not
                a mapping.
            ViyaResponseError: The response carried no usable decision id.
            ViyaAPIError: The server rejected the definition.
            ViyaError: On any other failure.
        """
        name = require_non_empty_str(name, "name")
        if not isinstance(flow, Mapping):
            raise ViyaConfigError("flow must be a mapping (e.g. {'steps': []})")
        body = self._dialect.build_decision_definition(
            name,
            description=description,
            flow=flow,
            signature=signature,
            properties=properties,
        )
        raw = self._http.request_json(
            "POST",
            self._dialect.decisions_flows_path(),
            accept=self._dialect.decision_media_type,
            content_type=self._dialect.decision_media_type,
            json_body=body,
            timeout=timeout,
        )
        decision_id = raw.get("id")
        if not isinstance(decision_id, str) or not decision_id.strip():
            raise ViyaResponseError(
                "decision create response carried no usable 'id' field",
                response_body=dict(raw),
            )
        return self._dialect.parse_decision(decision_id.strip(), raw)

    def update(
        self,
        decision_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        flow: Mapping[str, Any] | None = None,
        signature: Any | None = None,
        properties: Any | None = None,
        timeout: float | tuple[float, float] | None = None,
    ) -> Decision:
        """Update an existing decision flow.

        The decision-flow subresource is guarded by optimistic concurrency: the
        ``PUT`` must carry an ``If-Match`` ETag matching the flow's current
        revision or the server rejects it (HTTP 428). This method fetches the
        flow to read that ETag, overlays the fields you pass onto the flow's
        current authorable representation (so unspecified fields are preserved
        rather than wiped), then issues the guarded ``PUT`` — a concurrent change
        between the two calls surfaces as a precondition failure rather than a
        silent overwrite.

        Pass only the fields you want to change; at least one must be given.

        Args:
            decision_id: The id of the flow to update. Must already exist.
            name: New display name, if changing. Must be non-empty when given.
            description: New description, if changing.
            flow: New flow graph (raw mapping), if changing.
            signature: New decision signature, if changing.
            properties: New decision properties, if changing.
            timeout: Optional per-call timeout override.

        Returns:
            The parsed :class:`Decision` returned by the update.

        Raises:
            ViyaConfigError: ``decision_id`` is empty/not a string, no field was
                given to change, or ``name``/``flow`` has the wrong type.
            ViyaNotFoundError: No decision with that id exists.
            ViyaResponseError: The flow reported no usable ETag.
            ViyaAPIError: The server rejected the update (e.g. a 412 if the flow
                changed concurrently).
            ViyaError: On any other failure.
        """
        decision_id = require_identifier(decision_id, "decision_id")
        if all(field is None for field in (name, description, flow, signature, properties)):
            raise ViyaConfigError("update requires at least one field to change")
        # Validate the mutable-typed fields eagerly, before the network round
        # trip, so a bad value fails at the call site rather than after the GET.
        if name is not None:
            name = require_non_empty_str(name, "name")
        if flow is not None and not isinstance(flow, Mapping):
            raise ViyaConfigError("flow must be a mapping (e.g. {'steps': []})")

        # Fetch the current representation for its ETag (the concurrency guard)
        # and to overlay onto — unspecified fields are preserved, not dropped.
        current, response = self._http.request_json_with_response(
            "GET",
            self._dialect.decision_path(decision_id),
            accept=self._dialect.decision_media_type,
            timeout=timeout,
        )
        etag = response.headers.get("ETag")
        if not etag:
            raise ViyaResponseError(
                f"decision {decision_id!r} returned no ETag; cannot safely update "
                "it without the concurrency guard",
                response_body=current,
            )
        merged_name = require_non_empty_str(
            name if name is not None else current.get("name"), "name"
        )
        body = self._dialect.build_decision_definition(
            merged_name,
            description=description if description is not None else current.get("description"),
            flow=flow if flow is not None else current.get("flow"),
            signature=signature if signature is not None else current.get("signature"),
            properties=properties if properties is not None else current.get("properties"),
        )
        # The ETag comes back already quoted; the server requires the If-Match
        # value to keep those quotes, so forward the header value verbatim.
        raw = self._http.request_json(
            "PUT",
            self._dialect.decision_path(decision_id),
            accept=self._dialect.decision_media_type,
            content_type=self._dialect.decision_media_type,
            json_body=body,
            extra_headers={"If-Match": etag},
            timeout=timeout,
        )
        return self._dialect.parse_decision(decision_id, raw)

    def delete(
        self,
        decision_id: str,
        *,
        timeout: float | tuple[float, float] | None = None,
    ) -> None:
        """Delete a decision flow.

        Args:
            decision_id: The id of the flow to delete.
            timeout: Optional per-call timeout override.

        Raises:
            ViyaConfigError: ``decision_id`` is empty or not a string.
            ViyaNotFoundError: No decision with that id exists.
            ViyaError: On any other failure.
        """
        decision_id = require_identifier(decision_id, "decision_id")
        # DELETE returns 204 No Content; use request() (not request_json) so an
        # empty body isn't mistaken for a malformed JSON response.
        self._http.request(
            "DELETE",
            self._dialect.decision_path(decision_id),
            timeout=timeout,
        )

    def get_code(self, decision_id: str) -> str:
        """Fetch a decision flow's generated DS2 code (current revision).

        Returns the server-generated DS2 source for the flow's *current*
        revision as raw text — the same code the flow compiles to when scored.
        For the code at a specific historical revision, use
        :meth:`get_revision_code`.

        Args:
            decision_id: The decision id.

        Returns:
            The generated DS2 source, verbatim, as a string.

        Raises:
            ViyaConfigError: ``decision_id`` is empty or not a string.
            ViyaNotFoundError: No decision with that id exists.
            ViyaError: On any other failure.
        """
        decision_id = require_identifier(decision_id, "decision_id")
        return self._http.request_text(
            "GET",
            self._dialect.decision_code_path(decision_id),
            accept=self._dialect.decision_code_media_type,
        )

    def get_revision_code(self, decision_id: str, revision_id: str) -> str:
        """Fetch a decision flow's generated DS2 code *at a given revision*.

        Like :meth:`get_code`, but for a specific historical revision (see
        :meth:`revisions` for the ids). Returns the generated DS2 source as raw
        text.

        Args:
            decision_id: The decision id (the flow).
            revision_id: The revision id, e.g. from :meth:`revisions`.

        Returns:
            The generated DS2 source at that revision, verbatim, as a string.

        Raises:
            ViyaConfigError: Either id is empty or not a string.
            ViyaNotFoundError: No such decision or revision exists.
            ViyaError: On any other failure.
        """
        decision_id = require_identifier(decision_id, "decision_id")
        revision_id = require_identifier(revision_id, "revision_id")
        return self._http.request_text(
            "GET",
            self._dialect.decision_revision_code_path(decision_id, revision_id),
            accept=self._dialect.decision_code_media_type,
        )

    def external_artifacts(self, decision_id: str) -> tuple[ExternalArtifact, ...]:
        """Return the external artifacts a decision flow depends on (current revision).

        A decision flow can reference resources outside the flow itself — most
        commonly the analytic store backing a model step. Unlike :meth:`list` and
        :meth:`revisions`, this endpoint is **not** paginated: the server returns
        every artifact in one response, so this eagerly returns the full tuple
        rather than a lazy iterator.

        Args:
            decision_id: The decision id.

        Returns:
            A tuple of :class:`ExternalArtifact`, in server order (empty if the
            flow references none).

        Raises:
            ViyaConfigError: ``decision_id`` is empty or not a string.
            ViyaNotFoundError: No decision with that id exists.
            ViyaError: On any other failure.
        """
        decision_id = require_identifier(decision_id, "decision_id")
        return self._fetch_external_artifacts(
            self._dialect.decision_external_artifacts_path(decision_id)
        )

    def revision_external_artifacts(
        self, decision_id: str, revision_id: str
    ) -> tuple[ExternalArtifact, ...]:
        """Return the external artifacts of a flow *at a given revision*.

        Like :meth:`external_artifacts`, but for a specific historical revision
        (see :meth:`revisions` for the ids).

        Args:
            decision_id: The decision id (the flow).
            revision_id: The revision id, e.g. from :meth:`revisions`.

        Returns:
            A tuple of :class:`ExternalArtifact`, in server order.

        Raises:
            ViyaConfigError: Either id is empty or not a string.
            ViyaNotFoundError: No such decision or revision exists.
            ViyaError: On any other failure.
        """
        decision_id = require_identifier(decision_id, "decision_id")
        revision_id = require_identifier(revision_id, "revision_id")
        return self._fetch_external_artifacts(
            self._dialect.decision_revision_external_artifacts_path(decision_id, revision_id)
        )

    def _fetch_external_artifacts(self, path: str) -> tuple[ExternalArtifact, ...]:
        """Fetch and parse a (non-paginated) external-artifacts collection."""
        raw = self._http.request_json(
            "GET",
            path,
            accept=self._dialect.decision_external_artifacts_media_type,
        )
        items = raw.get("items")
        if not isinstance(items, list):
            return ()
        return tuple(
            self._dialect.parse_external_artifact(item)
            for item in items
            if isinstance(item, Mapping)
        )

    # -- revision/lock hooks (see RevisionsMixin) ---------------------------

    def _revisions_path(self, resource_id: str) -> str:
        return self._dialect.decision_revisions_path(resource_id)

    def _revision_path(self, resource_id: str, revision_id: str) -> str:
        return self._dialect.decision_revision_path(resource_id, revision_id)

    def _revision_media_type(self) -> str:
        return self._dialect.decision_media_type

    def _parse_revision_full(self, revision_id: str, raw: Mapping[str, Any]) -> Decision:
        # A full-revision payload is a decision at that revision — its own `id`
        # is the revision id, which parse_decision records as Decision.id.
        return self._dialect.parse_decision(revision_id, raw)
