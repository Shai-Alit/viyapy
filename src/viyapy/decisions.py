"""Operations on SAS Intelligent Decisioning decision flows."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

from ._http import HttpClient
from ._pagination import DEFAULT_PAGE_SIZE, iter_collection
from ._revisions import RevisionsMixin
from ._validation import require_identifier, require_positive_int
from .dialects.base import Dialect
from .models import Decision, DecisionSummary, ModelStep


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
