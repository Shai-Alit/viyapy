"""Operations on the SAS Micro Analytic Service (MAS)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ._http import HttpClient
from ._validation import require_identifier
from .dialects.base import DEFAULT_MAS_STEP, Dialect
from .models import ExecutionResult


class MASClient:
    """MAS module operations, accessed via ``ViyaClient.mas``."""

    def __init__(self, http: HttpClient, dialect: Dialect) -> None:
        self._http = http
        self._dialect = dialect

    def execute(
        self,
        module_id: str,
        inputs: Mapping[str, Any],
        *,
        step: str = DEFAULT_MAS_STEP,
        timeout: float | tuple[float, float] | None = None,
    ) -> ExecutionResult:
        """Execute a MAS module step against a mapping of inputs.

        Args:
            module_id: The published module id (for a published decision this is
                the module name; the step defaults to ``"execute"``).
            inputs: Feature name/value mapping. Serialized as JSON — values are
                passed through unchanged (no name-mangling).
            step: The module step to execute.
            timeout: Optional per-call timeout override (MAS execution may need a
                longer read timeout than a metadata GET).

        Returns:
            The parsed :class:`ExecutionResult`.

        Raises:
            ViyaConfigError: ``module_id`` or ``step`` is empty or not a string.
            ViyaNotFoundError: The module or step does not exist.
            ViyaResponseError: The response lacked an output list.
            ViyaError: On any other failure.
        """
        module_id = require_identifier(module_id, "module_id")
        step = require_identifier(step, "step")
        raw = self._http.request_json(
            "POST",
            self._dialect.mas_execute_path(module_id, step),
            content_type="application/json",
            json_body=self._dialect.build_inputs(inputs),
            timeout=timeout,
        )
        return self._dialect.parse_execution(module_id, step, raw)
