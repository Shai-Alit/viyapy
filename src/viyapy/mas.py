"""Operations on the SAS Micro Analytic Service (MAS)."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

from ._http import HttpClient
from ._pagination import iter_collection
from ._validation import (
    check_inputs_against_signature,
    require_identifier,
    require_positive_int,
)
from .dialects.base import DEFAULT_MAS_STEP, Dialect
from .models import ExecutionResult, MasModule, StepSignature

DEFAULT_PAGE_SIZE = 100


class MASClient:
    """MAS module operations, accessed via ``ViyaClient.mas``."""

    def __init__(self, http: HttpClient, dialect: Dialect) -> None:
        self._http = http
        self._dialect = dialect

    def list(self, *, page_size: int = DEFAULT_PAGE_SIZE) -> Iterator[MasModule]:
        """Iterate the MAS modules on the deployment, one per yielded item.

        Pages are fetched lazily as the iterator is consumed (following the
        collection's ``next`` links), so a large deployment is streamed rather
        than buffered. ``page_size`` is validated eagerly, when this method is
        called, so a bad value fails fast at the call site rather than on the
        first iteration.

        Args:
            page_size: Number of modules requested per page. Larger pages mean
                fewer round trips; the server may cap the effective size.

        Returns:
            An iterator over each :class:`MasModule`, in server order.

        Raises:
            ViyaConfigError: ``page_size`` is not a positive integer.
            ViyaError: On any request failure while paging.
        """
        # Validate eagerly here (not in the generator below): a generator
        # function defers its whole body until first iteration, which would
        # postpone this check and defeat the fail-fast contract.
        require_positive_int(page_size, "page_size")
        return self._iter_modules(page_size)

    def _iter_modules(self, page_size: int) -> Iterator[MasModule]:
        """Lazily page through the MAS module collection (see :meth:`list`)."""
        items = iter_collection(
            self._http,
            self._dialect.mas_modules_path(),
            params={"limit": page_size},
        )
        for item in items:
            yield self._dialect.parse_module(item)

    def get(self, module_id: str) -> MasModule:
        """Fetch a single MAS module's metadata.

        Args:
            module_id: The module id.

        Returns:
            The parsed :class:`MasModule`.

        Raises:
            ViyaConfigError: ``module_id`` is empty or not a string.
            ViyaNotFoundError: No module with that id exists.
            ViyaError: On any other failure.
        """
        module_id = require_identifier(module_id, "module_id")
        raw = self._http.request_json(
            "GET",
            self._dialect.mas_module_path(module_id),
            accept=self._dialect.mas_module_media_type,
        )
        return self._dialect.parse_module(raw)

    def get_signature(self, module_id: str, step: str = DEFAULT_MAS_STEP) -> StepSignature:
        """Fetch the input/output signature of a MAS module step.

        Use this to discover a step's expected inputs and outputs (names, types,
        dimensions) before calling :meth:`execute` — for example to validate a
        payload client-side or to build a form.

        Args:
            module_id: The module id.
            step: The step whose signature to fetch (defaults to ``"execute"``).

        Returns:
            The parsed :class:`StepSignature`.

        Raises:
            ViyaConfigError: ``module_id`` or ``step`` is empty or not a string.
            ViyaNotFoundError: No such module or step exists.
            ViyaResponseError: The response was not a usable step signature.
            ViyaError: On any other failure.
        """
        module_id = require_identifier(module_id, "module_id")
        step = require_identifier(step, "step")
        raw = self._http.request_json(
            "GET",
            self._dialect.mas_step_path(module_id, step),
            accept=self._dialect.mas_step_media_type,
        )
        return self._dialect.parse_step_signature(module_id, step, raw)

    def validate(
        self, module_id: str, inputs: Mapping[str, Any], *, step: str = DEFAULT_MAS_STEP
    ) -> StepSignature:
        """Validate ``inputs`` against a step's signature, without executing it.

        Fetches the step signature and checks that the supplied input names match
        what the step declares, raising :class:`~viyapy.exceptions.ViyaValidationError`
        if a declared input is missing or an undeclared input was supplied. Only the
        set of names is checked, not values or types. Useful as a pre-flight before
        :meth:`execute`, or to validate a form the user is filling in.

        Args:
            module_id: The module id.
            inputs: Feature name/value mapping to validate.
            step: The step whose signature to validate against (defaults to
                ``"execute"``).

        Returns:
            The fetched :class:`StepSignature` (so the caller can reuse it).

        Raises:
            ViyaConfigError: ``module_id`` or ``step`` is empty or not a string.
            ViyaNotFoundError: No such module or step exists.
            ViyaResponseError: The response was not a usable step signature.
            ViyaValidationError: The inputs do not match the signature.
            ViyaError: On any other failure.
        """
        signature = self.get_signature(module_id, step=step)
        check_inputs_against_signature(signature, inputs, module_id=module_id, step=step)
        return signature

    def execute(
        self,
        module_id: str,
        inputs: Mapping[str, Any],
        *,
        step: str = DEFAULT_MAS_STEP,
        validate: bool = False,
        timeout: float | tuple[float, float] | None = None,
    ) -> ExecutionResult:
        """Execute a MAS module step against a mapping of inputs.

        Args:
            module_id: The published module id (for a published decision this is
                the module name; the step defaults to ``"execute"``).
            inputs: Feature name/value mapping. Serialized as JSON — values are
                passed through unchanged (no name-mangling).
            step: The module step to execute.
            validate: When ``True``, fetch the step signature and validate the
                inputs against it before executing (an extra round trip), raising
                ``ViyaValidationError`` on a mismatch. Off by default so a normal
                execute stays a single request.
            timeout: Optional per-call timeout override (MAS execution may need a
                longer read timeout than a metadata GET).

        Returns:
            The parsed :class:`ExecutionResult`.

        Raises:
            ViyaConfigError: ``module_id`` or ``step`` is empty or not a string.
            ViyaNotFoundError: The module or step does not exist.
            ViyaResponseError: The response lacked an output list.
            ViyaValidationError: ``validate`` is set and the inputs do not match
                the step signature.
            ViyaError: On any other failure.
        """
        module_id = require_identifier(module_id, "module_id")
        step = require_identifier(step, "step")
        if validate:
            self.validate(module_id, inputs, step=step)
        raw = self._http.request_json(
            "POST",
            self._dialect.mas_execute_path(module_id, step),
            content_type="application/json",
            json_body=self._dialect.build_inputs(inputs),
            timeout=timeout,
        )
        return self._dialect.parse_execution(module_id, step, raw)
