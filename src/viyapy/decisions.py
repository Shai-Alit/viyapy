"""Operations on SAS Intelligent Decisioning decision flows."""

from __future__ import annotations

from ._http import HttpClient
from ._validation import require_identifier
from .dialects.base import Dialect
from .models import Decision, ModelStep


class DecisionsAPI:
    """Decision-flow operations, accessed via ``ViyaClient.decisions``."""

    def __init__(self, http: HttpClient, dialect: Dialect) -> None:
        self._http = http
        self._dialect = dialect

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
