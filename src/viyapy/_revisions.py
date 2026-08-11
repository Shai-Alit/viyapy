"""Reusable revision-history read operations for versioned Viya resources.

SAS Viya versions several resource types identically — decision flows and
business rulesets both expose a ``/revisions`` subcollection of lightweight
:class:`~viyapy.models.Revision` summaries, and each revision can be fetched in
full at ``/revisions/{revisionId}``. The ``checkout`` flag a revision carries is
the checked-out/lock indicator the later lock operations act on.

:class:`RevisionsMixin` factors that shared read shape out of the individual
resource APIs. A concrete API mixes it in, supplies the resource-specific paths,
media type, and full-payload parser via the four ``_revision*`` hooks, and gets
:meth:`~RevisionsMixin.revisions` and :meth:`~RevisionsMixin.get_revision` for
free. The full-fetch return type is generic (``FullT``) so each resource returns
its own domain object — a decision flow returns a
:class:`~viyapy.models.Decision`.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any, Generic, TypeVar

from ._http import HttpClient
from ._pagination import DEFAULT_PAGE_SIZE, iter_collection
from ._validation import require_identifier, require_positive_int
from .dialects.base import Dialect
from .models import Revision

# The domain object a full-revision fetch resolves to (e.g. Decision).
FullT = TypeVar("FullT")


class RevisionsMixin(Generic[FullT]):
    """Adds ``revisions`` / ``get_revision`` to a versioned-resource API.

    The mixing class must expose ``_http`` and ``_dialect`` attributes (every
    resource API sets these in ``__init__``) and implement the four ``_revision*``
    hooks below. Revision *summaries* are parsed by the shared
    :meth:`Dialect.parse_revision`; only the full-revision payload parsing is
    resource-specific (via :meth:`_parse_revision_full`).
    """

    # Provided by the concrete API's __init__; declared here for the type checker.
    _http: HttpClient
    _dialect: Dialect

    # -- hooks the concrete API supplies ------------------------------------

    def _revisions_path(self, resource_id: str) -> str:
        """Return the relative path of the resource's revisions collection."""
        raise NotImplementedError  # pragma: no cover - abstract hook

    def _revision_path(self, resource_id: str, revision_id: str) -> str:
        """Return the relative path of one revision of the resource."""
        raise NotImplementedError  # pragma: no cover - abstract hook

    def _revision_media_type(self) -> str:
        """Return the ``Accept`` media type for a full-revision fetch."""
        raise NotImplementedError  # pragma: no cover - abstract hook

    def _parse_revision_full(self, revision_id: str, raw: Mapping[str, Any]) -> FullT:
        """Parse a full-revision payload into the resource's domain object."""
        raise NotImplementedError  # pragma: no cover - abstract hook

    # -- public read operations ---------------------------------------------

    def revisions(
        self, resource_id: str, *, page_size: int = DEFAULT_PAGE_SIZE
    ) -> Iterator[Revision]:
        """Iterate a resource's revision history, newest-relevant first.

        Pages are fetched lazily as the iterator is consumed (following the
        collection's ``next`` links). Both arguments are validated eagerly, when
        this method is called, so a bad value fails fast at the call site rather
        than on the first iteration.

        Args:
            resource_id: The owning resource id (e.g. a decision flow id).
            page_size: Number of revisions requested per page. Larger pages mean
                fewer round trips; the server may cap the effective size.

        Returns:
            An iterator over each :class:`~viyapy.models.Revision`, in server
            order.

        Raises:
            ViyaConfigError: ``resource_id`` is empty/not a string, or
                ``page_size`` is not a positive integer.
            ViyaError: On any request failure while paging.
        """
        # Validate eagerly here (not in the generator below): a generator
        # function defers its whole body until first iteration, which would
        # postpone these checks and defeat the fail-fast contract.
        resource_id = require_identifier(resource_id, "resource_id")
        require_positive_int(page_size, "page_size")
        return self._iter_revisions(resource_id, page_size)

    def _iter_revisions(self, resource_id: str, page_size: int) -> Iterator[Revision]:
        """Lazily page through the revisions collection (see :meth:`revisions`)."""
        items = iter_collection(
            self._http,
            self._revisions_path(resource_id),
            params={"limit": page_size},
        )
        for item in items:
            yield self._dialect.parse_revision(item)

    def get_revision(self, resource_id: str, revision_id: str) -> FullT:
        """Fetch the resource's full content at a specific revision.

        Args:
            resource_id: The owning resource id (e.g. a decision flow id).
            revision_id: The revision id (e.g. a :attr:`Revision.id`).

        Returns:
            The resource's domain object at that revision (e.g. a
            :class:`~viyapy.models.Decision`).

        Raises:
            ViyaConfigError: Either id is empty or not a string.
            ViyaNotFoundError: No such resource or revision exists.
            ViyaError: On any other failure.
        """
        resource_id = require_identifier(resource_id, "resource_id")
        revision_id = require_identifier(revision_id, "revision_id")
        raw = self._http.request_json(
            "GET",
            self._revision_path(resource_id, revision_id),
            accept=self._revision_media_type(),
        )
        return self._parse_revision_full(revision_id, raw)
