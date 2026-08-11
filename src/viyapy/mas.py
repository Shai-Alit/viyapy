"""Operations on the SAS Micro Analytic Service (MAS)."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

from ._http import HttpClient
from ._pagination import iter_collection
from ._polling import DEFAULT_POLL_INTERVAL, DEFAULT_POLL_TIMEOUT, poll_until
from ._validation import (
    check_inputs_against_signature,
    optional_identifier,
    require_identifier,
    require_non_empty_str,
    require_non_negative_int,
    require_positive_int,
)
from .dialects.base import DEFAULT_MAS_STEP, Dialect
from .exceptions import (
    ViyaConfigError,
    ViyaJobError,
    ViyaResponseError,
    ViyaValidationError,
)
from .models import (
    CompileJob,
    ExecutionResult,
    MasModule,
    ModuleSource,
    StepSignature,
    ValidationResult,
)

DEFAULT_PAGE_SIZE = 100
DEFAULT_SCOPE = "public"

# Friendly ``language`` keyword -> the source-language media type MAS expects in a
# module definition's / source-update's ``type`` field. MAS reports the same
# languages back on a module payload's ``language`` field, so this also maps a
# fetched module's language to the media type for a subsequent source update.
_SOURCE_TYPE_BY_LANGUAGE = {
    "ds2": "text/vnd.sas.source.ds2",
    "python": "text/x-python",
}


def _source_type_for_language(language: str, param: str) -> str:
    """Map a ``language`` keyword to its MAS source media type, or raise."""
    key = language.strip().lower() if isinstance(language, str) else language
    source_type = _SOURCE_TYPE_BY_LANGUAGE.get(key)
    if source_type is None:
        supported = ", ".join(sorted(_SOURCE_TYPE_BY_LANGUAGE))
        raise ViyaConfigError(f"{param} must be one of: {supported} (got {language!r})")
    return source_type


def _build_metadata(client_id: str | None, transaction_id: str | None) -> dict[str, str] | None:
    """Build the request ``metadata`` object, or ``None`` if no ids were given.

    MAS reads correlation ids from snake_case ``client_id``/``transaction_id``
    keys inside a ``metadata`` object and echoes them on the response; omitted
    ids are left out entirely rather than sent as ``null``.
    """
    metadata: dict[str, str] = {}
    if client_id is not None:
        metadata["client_id"] = client_id
    if transaction_id is not None:
        metadata["transaction_id"] = transaction_id
    return metadata or None


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

    def create(
        self,
        module_id: str,
        source: str,
        *,
        language: str = "ds2",
        scope: str = DEFAULT_SCOPE,
        description: str | None = None,
        wait: bool = False,
        poll_timeout: float = DEFAULT_POLL_TIMEOUT,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        timeout: float | tuple[float, float] | None = None,
    ) -> MasModule:
        """Create a new MAS module from source code.

        Compiles ``source`` server-side into a module identified by ``module_id``.
        The module then exposes callable steps (typically ``execute``) that
        :meth:`execute` can run.

        Two compilation paths are available, selected by ``wait``:

        - ``wait=False`` (default) — a single synchronous ``POST /modules``: the
          server compiles the source in the request and returns the finished
          module. A compile error surfaces as a :class:`ViyaAPIError`.
        - ``wait=True`` — submit an asynchronous compile *job* (see
          :meth:`submit_compile_job`) and block until it finishes, then fetch and
          return the compiled module. A job that fails to compile surfaces as a
          :class:`~viyapy.exceptions.ViyaJobError` carrying the compiler
          diagnostics, rather than an HTTP error. Use this for sources whose
          compilation is slow enough to risk an HTTP read timeout, or when you
          want the job's structured diagnostics; ``poll_timeout`` and
          ``poll_interval`` tune the wait (see :meth:`wait_for_job`).

        Args:
            module_id: The id to create the module under. Must be a non-empty
                string; a module with this id must not already exist.
            source: The module source code (DS2 or Python), sent verbatim.
            language: Source language — ``"ds2"`` (default) or ``"python"`` —
                selecting the source media type MAS compiles the body as.
            scope: Module scope; MAS requires one (defaults to ``"public"``).
            description: Optional human-readable description.
            wait: When ``True``, compile asynchronously via a job and block until
                it completes (see above). Defaults to ``False`` (synchronous).
            poll_timeout: Overall wait budget in seconds when ``wait=True``
                (ignored otherwise). Defaults to :data:`DEFAULT_POLL_TIMEOUT`.
            poll_interval: Delay between job polls in seconds when ``wait=True``
                (ignored otherwise). Defaults to :data:`DEFAULT_POLL_INTERVAL`.
            timeout: Optional per-call timeout override for each HTTP request
                (compilation may need a longer read timeout than a metadata GET).

        Returns:
            The parsed :class:`MasModule` for the freshly created module.

        Raises:
            ViyaConfigError: ``module_id``/``scope`` is empty or not a string,
                ``source`` is empty, ``language`` is not supported, or (when
                ``wait=True``) ``poll_timeout``/``poll_interval`` is not positive.
            ViyaAPIError: The server rejected the definition (e.g. a synchronous
                compile error or an id that already exists).
            ViyaJobError: ``wait=True`` and the compile job finished ``failed``
                (carries the compiler diagnostics).
            ViyaPollTimeoutError: ``wait=True`` and the job did not finish within
                ``poll_timeout``.
            ViyaError: On any other failure.
        """
        if wait:
            job = self.submit_compile_job(
                module_id,
                source,
                language=language,
                scope=scope,
                description=description,
                timeout=timeout,
            )
            job = self.wait_for_job(
                job.id,
                poll_timeout=poll_timeout,
                poll_interval=poll_interval,
                raise_on_failure=True,
                timeout=timeout,
            )
            # The job completed; the compiled module now exists. Prefer the id the
            # job reports (authoritative) but fall back to the requested one.
            compiled_id = job.module_id or require_identifier(module_id, "module_id")
            return self.get(compiled_id)

        module_id = require_identifier(module_id, "module_id")
        source = require_non_empty_str(source, "source")
        scope = require_identifier(scope, "scope")
        source_type = _source_type_for_language(language, "language")
        body = self._dialect.build_module_definition(
            module_id,
            source,
            source_type=source_type,
            scope=scope,
            description=description,
        )
        raw = self._http.request_json(
            "POST",
            self._dialect.mas_modules_path(),
            accept=self._dialect.mas_module_media_type,
            content_type=self._dialect.mas_module_definition_media_type,
            json_body=body,
            timeout=timeout,
        )
        return self._dialect.parse_module(raw)

    def get_source(
        self,
        module_id: str,
        *,
        timeout: float | tuple[float, float] | None = None,
    ) -> ModuleSource:
        """Fetch a MAS module's source code.

        Args:
            module_id: The module id.
            timeout: Optional per-call timeout override.

        Returns:
            The parsed :class:`ModuleSource`.

        Raises:
            ViyaConfigError: ``module_id`` is empty or not a string.
            ViyaNotFoundError: No module with that id exists.
            ViyaResponseError: The response was not a usable source payload.
            ViyaError: On any other failure.
        """
        module_id = require_identifier(module_id, "module_id")
        raw = self._http.request_json(
            "GET",
            self._dialect.mas_module_source_path(module_id),
            accept=self._dialect.mas_module_source_media_type,
            timeout=timeout,
        )
        return self._dialect.parse_module_source(module_id, raw)

    def update_source(
        self,
        module_id: str,
        source: str,
        *,
        language: str | None = None,
        timeout: float | tuple[float, float] | None = None,
    ) -> ModuleSource:
        """Replace a MAS module's source code, recompiling it in place.

        MAS guards the source subresource with optimistic concurrency: the update
        must carry an ``If-Match`` ETag matching the module's current revision, or
        the server rejects it (HTTP 428). This method fetches the module to obtain
        that ETag (and, when ``language`` is not given, to reuse the module's
        current language) and then issues the guarded ``PUT`` — so a concurrent
        change between the two calls surfaces as a precondition failure rather
        than a silent overwrite.

        Args:
            module_id: The id of the module to update. Must already exist.
            source: The new source code, sent verbatim.
            language: Source language of ``source`` — ``"ds2"`` or ``"python"``.
                When ``None`` (default), the module's current language is reused,
                which is the common case (updating a module in the same language).
            timeout: Optional per-call timeout override.

        Returns:
            The parsed :class:`ModuleSource` returned by the update.

        Raises:
            ViyaConfigError: ``module_id`` is empty or not a string, ``source`` is
                empty, or an explicit ``language`` is not supported.
            ViyaNotFoundError: No module with that id exists.
            ViyaResponseError: The module reported no usable ETag or language, or
                the update response was not a usable source payload.
            ViyaAPIError: The server rejected the update (e.g. a compile error, or
                a 428 if the module changed concurrently).
            ViyaError: On any other failure.
        """
        module_id = require_identifier(module_id, "module_id")
        source = require_non_empty_str(source, "source")
        # Validate an explicit language before the network round trip, so a bad
        # value fails fast at the call site rather than after the module GET.
        explicit_source_type = (
            _source_type_for_language(language, "language") if language is not None else None
        )

        # Fetch the module to get its current ETag (for If-Match) and, when the
        # caller didn't specify one, its language (to pick the source media type).
        module_raw, response = self._http.request_json_with_response(
            "GET",
            self._dialect.mas_module_path(module_id),
            accept=self._dialect.mas_module_media_type,
            timeout=timeout,
        )
        etag = response.headers.get("ETag")
        if not etag:
            raise ViyaResponseError(
                f"MAS module {module_id!r} returned no ETag; cannot safely update "
                "its source without the concurrency guard",
                response_body=module_raw,
            )
        if explicit_source_type is not None:
            source_type = explicit_source_type
        else:
            current = module_raw.get("language")
            if not isinstance(current, str) or not current.strip():
                raise ViyaResponseError(
                    f"MAS module {module_id!r} reported no language; pass language= "
                    "explicitly to update its source",
                    response_body=module_raw,
                )
            source_type = _source_type_for_language(current, "language")

        body = self._dialect.build_source_update(module_id, source, source_type=source_type)
        # The ETag comes back already quoted (e.g. '"msnrvegr"'); MAS requires the
        # If-Match value to keep those quotes, so forward the header value verbatim.
        raw = self._http.request_json(
            "PUT",
            self._dialect.mas_module_source_path(module_id),
            accept=self._dialect.mas_module_source_media_type,
            content_type=self._dialect.mas_module_source_media_type,
            json_body=body,
            extra_headers={"If-Match": etag},
            timeout=timeout,
        )
        return self._dialect.parse_module_source(module_id, raw)

    def delete(
        self,
        module_id: str,
        *,
        timeout: float | tuple[float, float] | None = None,
    ) -> None:
        """Delete a MAS module.

        Args:
            module_id: The id of the module to delete.
            timeout: Optional per-call timeout override.

        Raises:
            ViyaConfigError: ``module_id`` is empty or not a string.
            ViyaNotFoundError: No module with that id exists.
            ViyaError: On any other failure.
        """
        module_id = require_identifier(module_id, "module_id")
        # DELETE returns 204 No Content; use request() (not request_json) so an
        # empty body isn't mistaken for a malformed JSON response.
        self._http.request(
            "DELETE",
            self._dialect.mas_module_path(module_id),
            timeout=timeout,
        )

    def submit_compile_job(
        self,
        module_id: str,
        source: str,
        *,
        language: str = "ds2",
        scope: str = DEFAULT_SCOPE,
        description: str | None = None,
        timeout: float | tuple[float, float] | None = None,
    ) -> CompileJob:
        """Submit an asynchronous job to compile a module, without waiting.

        Posts the same module definition as :meth:`create` to the MAS compile-job
        collection (``POST /microanalyticScore/jobs``), which accepts it (HTTP 202)
        and compiles the module in the background. This returns immediately with a
        :class:`~viyapy.models.CompileJob` in a non-terminal state (typically
        ``pending``); poll it with :meth:`get_job`, or use :meth:`wait_for_job` to
        block until it settles. For the common submit-and-block case, prefer
        ``create(..., wait=True)``.

        Note that a *grossly* malformed source (one MAS cannot even parse into a
        DS2 package) is still rejected synchronously here as an HTTP 400 rather
        than accepted as a job; a source that parses but fails to compile is
        accepted and later reaches a ``failed`` state on the job.

        Args:
            module_id: The id to compile the module under. Must be a non-empty
                string; a module with this id must not already exist.
            source: The module source code (DS2 or Python), sent verbatim.
            language: Source language — ``"ds2"`` (default) or ``"python"``.
            scope: Module scope; MAS requires one (defaults to ``"public"``).
            description: Optional human-readable description.
            timeout: Optional per-call timeout override.

        Returns:
            The parsed :class:`~viyapy.models.CompileJob` (usually ``pending``).

        Raises:
            ViyaConfigError: ``module_id``/``scope`` is empty or not a string,
                ``source`` is empty, or ``language`` is not supported.
            ViyaResponseError: The 202 response carried no usable job payload.
            ViyaAPIError: The server rejected the submission (e.g. an unparseable
                source, or an id that already exists).
            ViyaError: On any other failure.
        """
        module_id = require_identifier(module_id, "module_id")
        source = require_non_empty_str(source, "source")
        scope = require_identifier(scope, "scope")
        source_type = _source_type_for_language(language, "language")
        # A compile job is submitted with the same module.definition body as a
        # synchronous create; only the Accept/response envelope differs.
        body = self._dialect.build_module_definition(
            module_id,
            source,
            source_type=source_type,
            scope=scope,
            description=description,
        )
        raw = self._http.request_json(
            "POST",
            self._dialect.mas_jobs_path(),
            accept=self._dialect.mas_job_media_type,
            content_type=self._dialect.mas_module_definition_media_type,
            json_body=body,
            timeout=timeout,
        )
        return self._dialect.parse_compile_job(raw)

    def get_job(
        self,
        job_id: str,
        *,
        timeout: float | tuple[float, float] | None = None,
    ) -> CompileJob:
        """Fetch the current state of a MAS compile job.

        Args:
            job_id: The id of a job returned by :meth:`submit_compile_job`.
            timeout: Optional per-call timeout override.

        Returns:
            The parsed :class:`~viyapy.models.CompileJob` in its current state.

        Raises:
            ViyaConfigError: ``job_id`` is empty or not a string.
            ViyaNotFoundError: No job with that id exists.
            ViyaResponseError: The response was not a usable job payload.
            ViyaError: On any other failure.
        """
        job_id = require_identifier(job_id, "job_id")
        raw = self._http.request_json(
            "GET",
            self._dialect.mas_job_path(job_id),
            accept=self._dialect.mas_job_media_type,
            timeout=timeout,
        )
        return self._dialect.parse_compile_job(raw)

    def wait_for_job(
        self,
        job_id: str,
        *,
        poll_timeout: float = DEFAULT_POLL_TIMEOUT,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        raise_on_failure: bool = True,
        timeout: float | tuple[float, float] | None = None,
    ) -> CompileJob:
        """Poll a compile job until it finishes, or the wait budget expires.

        Repeatedly calls :meth:`get_job` (starting immediately, then every
        ``poll_interval`` seconds) until the job reaches a terminal state
        (``completed`` or ``failed``), then returns it. A job that finishes
        ``failed`` is, by default, surfaced as a
        :class:`~viyapy.exceptions.ViyaJobError` carrying the compiler diagnostics;
        pass ``raise_on_failure=False`` to instead return the failed
        :class:`~viyapy.models.CompileJob` and inspect ``.failed``/``.errors``
        yourself (mirroring ``validate_remote(raise_on_invalid=False)``).

        A timeout does not cancel the job — it may still finish server-side, so a
        caller can re-poll the same ``job_id`` to keep waiting.

        Args:
            job_id: The id of a job returned by :meth:`submit_compile_job`.
            poll_timeout: Overall wait budget in seconds (must be positive).
            poll_interval: Delay between polls in seconds (must be positive).
            raise_on_failure: When ``True`` (default), raise ``ViyaJobError`` if the
                job finishes ``failed``. When ``False``, return the failed job.
            timeout: Optional per-call HTTP timeout override for each poll.

        Returns:
            The terminal :class:`~viyapy.models.CompileJob` (``completed``, or
            ``failed`` when ``raise_on_failure=False``).

        Raises:
            ViyaConfigError: ``job_id`` is empty, or ``poll_timeout``/
                ``poll_interval`` is not a positive number.
            ViyaNotFoundError: No job with that id exists.
            ViyaResponseError: A poll response was not a usable job payload.
            ViyaJobError: ``raise_on_failure`` is set and the job finished failed.
            ViyaPollTimeoutError: The job did not finish within ``poll_timeout``.
            ViyaError: On any other failure.
        """
        job_id = require_identifier(job_id, "job_id")
        job = poll_until(
            lambda: self.get_job(job_id, timeout=timeout),
            lambda j: j.done,
            timeout=poll_timeout,
            interval=poll_interval,
            describe=lambda j: j.state or "unknown",
        )
        if raise_on_failure and job.failed:
            detail = "; ".join(job.errors) if job.errors else "the job reported no diagnostics"
            raise ViyaJobError(
                f"MAS compile job {job.id!r} for module "
                f"{job.module_id or '<unknown>'!r} failed: {detail}",
                job_id=job.id,
                module_id=job.module_id,
                state=job.state,
                errors=job.errors,
                response_body=job.raw,
            )
        return job

    def get_signature(
        self,
        module_id: str,
        step: str = DEFAULT_MAS_STEP,
        *,
        timeout: float | tuple[float, float] | None = None,
    ) -> StepSignature:
        """Fetch the input/output signature of a MAS module step.

        Use this to discover a step's expected inputs and outputs (names, types,
        dimensions) before calling :meth:`execute` — for example to validate a
        payload client-side or to build a form.

        Args:
            module_id: The module id.
            step: The step whose signature to fetch (defaults to ``"execute"``).
            timeout: Optional per-call timeout override for the signature request.

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
            timeout=timeout,
        )
        return self._dialect.parse_step_signature(module_id, step, raw)

    def validate(
        self,
        module_id: str,
        inputs: Mapping[str, Any],
        *,
        step: str = DEFAULT_MAS_STEP,
        timeout: float | tuple[float, float] | None = None,
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
            timeout: Optional per-call timeout override for the signature request.

        Returns:
            The fetched :class:`StepSignature` (so the caller can reuse it).

        Raises:
            ViyaConfigError: ``module_id`` or ``step`` is empty or not a string.
            ViyaNotFoundError: No such module or step exists.
            ViyaResponseError: The response was not a usable step signature.
            ViyaValidationError: The inputs do not match the signature.
            ViyaError: On any other failure.
        """
        signature = self.get_signature(module_id, step=step, timeout=timeout)
        check_inputs_against_signature(signature, inputs, module_id=module_id, step=step)
        return signature

    def validate_remote(
        self,
        module_id: str,
        inputs: Mapping[str, Any],
        *,
        step: str = DEFAULT_MAS_STEP,
        raise_on_invalid: bool = True,
        timeout: float | tuple[float, float] | None = None,
    ) -> ValidationResult:
        """Validate ``inputs`` against a step server-side, without executing it.

        Posts the inputs to the MAS validations endpoint so SAS Viya itself checks
        them against the step's signature — a stronger check than the client-side
        name comparison in :meth:`validate`, since the server also inspects types
        and constraints. A single round trip, no signature fetch.

        SAS reports an invalid payload as an HTTP 201 whose body says
        ``valid: false`` (not as a 4xx). By default that is surfaced as a
        :class:`~viyapy.exceptions.ViyaValidationError` carrying the server's
        messages; pass ``raise_on_invalid=False`` to instead return the
        :class:`~viyapy.models.ValidationResult` and inspect ``.valid`` yourself.

        Args:
            module_id: The module id.
            inputs: Feature name/value mapping to validate.
            step: The step to validate against (defaults to ``"execute"``).
            raise_on_invalid: When ``True`` (default), raise ``ViyaValidationError``
                if the server reports the inputs invalid. When ``False``, return the
                result regardless so the caller can branch on ``.valid``.
            timeout: Optional per-call timeout override.

        Returns:
            The parsed :class:`~viyapy.models.ValidationResult`.

        Raises:
            ViyaConfigError: ``module_id`` or ``step`` is empty or not a string.
            ViyaNotFoundError: No such module or step exists.
            ViyaResponseError: The response was not a usable validation result.
            ViyaValidationError: ``raise_on_invalid`` is set and the server reports
                the inputs invalid.
            ViyaError: On any other failure.
        """
        module_id = require_identifier(module_id, "module_id")
        step = require_identifier(step, "step")
        raw = self._http.request_json(
            "POST",
            self._dialect.mas_validation_path(module_id, step),
            accept=self._dialect.mas_validation_media_type,
            content_type=self._dialect.mas_step_input_media_type,
            json_body=self._dialect.build_inputs(inputs),
            timeout=timeout,
        )
        result = self._dialect.parse_validation(module_id, step, raw)
        if raise_on_invalid and not result.valid:
            detail = (
                "; ".join(result.messages)
                if result.messages
                else "the server did not accept the inputs"
            )
            raise ViyaValidationError(
                f"MAS rejected the inputs for module {module_id!r} step {step!r}: {detail}",
                messages=result.messages,
                module_id=module_id,
                step=step,
                response_body=result.raw,
            )
        return result

    def execute(
        self,
        module_id: str,
        inputs: Mapping[str, Any],
        *,
        step: str = DEFAULT_MAS_STEP,
        validate: bool = False,
        wait_time: int | None = None,
        client_id: str | None = None,
        transaction_id: str | None = None,
        timeout: float | tuple[float, float] | None = None,
    ) -> ExecutionResult:
        """Execute a MAS module step against a mapping of inputs.

        ``wait_time`` selects the execution mode (it maps to the server's
        ``waitTime`` query parameter, in milliseconds):

        - ``None`` (default) — synchronous: wait until execution completes; the
          result carries the ``outputs`` and ``execution_state == "completed"``.
        - a positive integer — timed: wait up to that many milliseconds. If the
          run finishes in time the result is ``completed`` with ``outputs``;
          otherwise ``outputs`` is empty and ``execution_state == "timedOut"``
          (see :attr:`ExecutionResult.timed_out`).
        - ``0`` — fire-and-forget: return immediately after validation with empty
          ``outputs`` and ``execution_state == "submitted"``. See :meth:`submit`
          for a named shortcut.

        Binary inputs are passed as ``bytes`` (or ``bytearray``) values in
        ``inputs``: they are base64-encoded on the wire with ``encoding: "b64"``,
        which MAS accepts for ``binary``/``any``-typed variables. Binary outputs
        are decoded back into ``bytes`` on :attr:`ExecutionResult.outputs`.

        Args:
            module_id: The published module id (for a published decision this is
                the module name; the step defaults to ``"execute"``).
            inputs: Feature name/value mapping. Serialized as JSON — scalar values
                are passed through unchanged (no name-mangling); ``bytes``/
                ``bytearray`` values are sent as base64-encoded binary.
            step: The module step to execute.
            validate: When ``True``, fetch the step signature and validate the
                inputs against it before executing (an extra round trip), raising
                ``ViyaValidationError`` on a mismatch. Off by default so a normal
                execute stays a single request. Any ``timeout`` override applies
                to the signature request as well as the execute request.
            wait_time: Server-side wait budget in milliseconds selecting the
                execution mode (see above). Must be a non-negative integer when
                given. This is distinct from ``timeout``, which bounds the HTTP
                call itself.
            client_id: Optional correlation id sent in the request ``metadata`` and
                echoed on :attr:`ExecutionResult.client_id`. Must be a non-empty
                string when given.
            transaction_id: Optional correlation id sent in the request ``metadata``
                and echoed on :attr:`ExecutionResult.transaction_id`. Must be a
                non-empty string when given.
            timeout: Optional per-call timeout override (MAS execution may need a
                longer read timeout than a metadata GET).

        Returns:
            The parsed :class:`ExecutionResult`.

        Raises:
            ViyaConfigError: ``module_id``/``step`` is empty or not a string,
                ``wait_time`` is not a non-negative integer, or ``client_id``/
                ``transaction_id`` is given but not a non-empty string.
            ViyaNotFoundError: The module or step does not exist.
            ViyaResponseError: A completed response lacked an output list.
            ViyaValidationError: ``validate`` is set and the inputs do not match
                the step signature.
            ViyaError: On any other failure.
        """
        module_id = require_identifier(module_id, "module_id")
        step = require_identifier(step, "step")
        client_id = optional_identifier(client_id, "client_id")
        transaction_id = optional_identifier(transaction_id, "transaction_id")
        params: dict[str, Any] | None = None
        if wait_time is not None:
            params = {"waitTime": require_non_negative_int(wait_time, "wait_time")}
        if validate:
            self.validate(module_id, inputs, step=step, timeout=timeout)
        metadata = _build_metadata(client_id, transaction_id)
        raw = self._http.request_json(
            "POST",
            self._dialect.mas_execute_path(module_id, step),
            content_type="application/json",
            json_body=self._dialect.build_inputs(inputs, metadata=metadata),
            params=params,
            timeout=timeout,
        )
        return self._dialect.parse_execution(module_id, step, raw)

    def submit(
        self,
        module_id: str,
        inputs: Mapping[str, Any],
        *,
        step: str = DEFAULT_MAS_STEP,
        validate: bool = False,
        client_id: str | None = None,
        transaction_id: str | None = None,
        timeout: float | tuple[float, float] | None = None,
    ) -> ExecutionResult:
        """Submit a MAS step for fire-and-forget execution, without waiting.

        A convenience for :meth:`execute` with ``wait_time=0``: the call returns
        as soon as the server accepts the inputs, so the result has empty
        ``outputs`` and ``execution_state == "submitted"`` (see
        :attr:`ExecutionResult.submitted`). Use this to kick off a run whose
        outputs you do not need in-band. MAS does not expose a per-execution
        result-polling endpoint, so the outputs are not retrievable afterward.

        Args:
            module_id: The published module id.
            inputs: Feature name/value mapping (``bytes`` values sent as binary).
            step: The module step to execute.
            validate: When ``True``, validate the inputs against the step
                signature before submitting (an extra round trip).
            client_id: Optional correlation id sent in the request ``metadata``.
            transaction_id: Optional correlation id sent in the request
                ``metadata``.
            timeout: Optional per-call timeout override.

        Returns:
            The parsed :class:`ExecutionResult`, with ``submitted`` set.

        Raises:
            ViyaConfigError: ``module_id`` or ``step`` is empty or not a string,
                or ``client_id``/``transaction_id`` is given but not a non-empty
                string.
            ViyaNotFoundError: The module or step does not exist.
            ViyaValidationError: ``validate`` is set and the inputs do not match
                the step signature.
            ViyaError: On any other failure.
        """
        return self.execute(
            module_id,
            inputs,
            step=step,
            validate=validate,
            wait_time=0,
            client_id=client_id,
            transaction_id=transaction_id,
            timeout=timeout,
        )
