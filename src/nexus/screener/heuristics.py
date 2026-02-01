"""Heuristic filters for document screening.

This module provides simple functions to perform a first-pass filter
over retrieved documents before invoking large language models. The
heuristics look for the presence of plant-disease related keywords
and absence of obviously off-topic terms. These filters are not
foolproof but help reduce the number of documents passed to the
expensive LLM stage.

Functions
---------
filter_documents(documents, include_patterns, exclude_patterns)
    Yield documents that contain at least one inclusion pattern and no
    exclusion patterns in their title or abstract.
"""

import re
from typing import Iterable, Iterator, List, Sequence

from nexus.core.models import Document


def _textify(doc: Document) -> str:
    """Concatenate title and abstract for keyword searching."""
    return f"{doc.title or ''} {doc.abstract or ''}".lower()


def filter_documents(
    documents: Iterable[Document],
    include_patterns: List[str] | None = None,
    exclude_patterns: List[str] | None = None,
    include_groups: Sequence[Sequence[str]] | None = None,
) -> Iterator[Document]:
    """Yield documents that match heuristic inclusion/exclusion criteria.

    Parameters
    ----------
    documents : Iterable[Document]
        Sequence of documents to filter.
    include_patterns : List[str], optional
        Lowercase keywords any of which must appear in the document's text.
        Ignored if include_groups is provided.
    exclude_patterns : List[str], optional
        Lowercase keywords none of which may appear in the document's text.
    include_groups : Sequence[Sequence[str]], optional
        Groups of keywords where at least one term from each group must
        appear in the document's text.

    Yields
    ------
    Document
        Documents deemed relevant by simple heuristics.
    """
    include_patterns = include_patterns or []
    exclude_patterns = exclude_patterns or []
    includes = [re.compile(p, re.IGNORECASE) for p in include_patterns]
    excludes = [re.compile(p, re.IGNORECASE) for p in exclude_patterns]
    group_patterns: List[List[re.Pattern[str]]] = []
    if include_groups:
        group_patterns = [
            [re.compile(p, re.IGNORECASE) for p in group] for group in include_groups
        ]

    for doc in documents:
        text = _textify(doc)
        if group_patterns:
            # Must match at least one term from each group.
            if not all(any(p.search(text) for p in group) for group in group_patterns):
                continue
        elif includes:
            # Must match at least one include.
            if not any(p.search(text) for p in includes):
                continue
        # Must not match any exclude.
        if any(p.search(text) for p in excludes):
            continue
        yield doc
