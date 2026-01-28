"""
Query translation framework for Simple SLR.

This module provides utilities for translating generic Query objects
into provider-specific query formats, including Boolean query parsing,
field mapping, and syntax adaptation.
"""

import logging
import re
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional

from nexus.core.models import Query

logger = logging.getLogger(__name__)


class BooleanOperator(str, Enum):
    """Boolean operators for query composition."""

    AND = "AND"
    OR = "OR"
    NOT = "NOT"


class QueryField(str, Enum):
    """Standard query fields."""

    TITLE = "title"
    ABSTRACT = "abstract"
    FULL_TEXT = "full_text"
    AUTHOR = "author"
    YEAR = "year"
    VENUE = "venue"
    DOI = "doi"
    KEYWORD = "keyword"
    ANY = "any"  # Search all fields


class QueryToken:
    """Represents a token in a parsed query.

    Attributes:
        value: Token value (term or operator)
        field: Field this token applies to
        is_phrase: Whether this is a phrase (quoted)
        is_operator: Whether this is a Boolean operator
    """

    def __init__(
        self,
        value: str,
        field: Optional[QueryField] = None,
        is_phrase: bool = False,
        is_operator: bool = False,
    ):
        self.value = value
        self.field = field or QueryField.ANY
        self.is_phrase = is_phrase
        self.is_operator = is_operator

    def __repr__(self) -> str:
        return f"QueryToken({self.value!r}, field={self.field}, phrase={self.is_phrase})"


class QueryParser:
    """Parser for Boolean query syntax.

    Parses queries like:
    - "machine learning" AND (deep OR neural)
    - title:"systematic review" AND year:2020
    - author:Smith NOT title:meta-analysis

    Example:
        >>> parser = QueryParser()
        >>> tokens = parser.parse('title:"ML" AND year:2020')
        >>> for token in tokens:
        ...     print(token)
    """

    # Regex patterns
    FIELD_PATTERN = re.compile(r"(\w+):")
    PHRASE_PATTERN = re.compile(r'"([^"]*)"')
    OPERATOR_PATTERN = re.compile(r"\b(AND|OR|NOT)\b", re.IGNORECASE)
    PAREN_PATTERN = re.compile(r"[()]")

    def parse(self, query_text: str) -> List[QueryToken]:
        """Parse query text into tokens.

        Args:
            query_text: Query string to parse

        Returns:
            List of QueryToken objects

        Example:
            >>> parser = QueryParser()
            >>> tokens = parser.parse('title:"ML" AND deep learning')
            >>> len(tokens)
            4
        """
        tokens = []
        remaining = query_text
        current_field = None

        while remaining.strip():
            remaining = remaining.strip()

            # Check for parentheses FIRST (before word matching)
            if remaining[0] in "()":
                paren = remaining[0]
                tokens.append(QueryToken(paren, is_operator=True))
                remaining = remaining[1:]
                continue

            # Check for field specification
            field_match = self.FIELD_PATTERN.match(remaining)
            if field_match:
                field_name = field_match.group(1).lower()
                try:
                    current_field = QueryField(field_name)
                except ValueError:
                    logger.warning(f"Unknown field: {field_name}, using 'any'")
                    current_field = QueryField.ANY
                remaining = remaining[field_match.end() :]
                continue

            # Check for quoted phrases
            phrase_match = self.PHRASE_PATTERN.match(remaining)
            if phrase_match:
                phrase = phrase_match.group(1)
                tokens.append(QueryToken(phrase, field=current_field, is_phrase=True))
                remaining = remaining[phrase_match.end() :]
                current_field = None
                continue

            # Check for Boolean operators
            operator_match = self.OPERATOR_PATTERN.match(remaining)
            if operator_match:
                operator = operator_match.group(1).upper()
                tokens.append(QueryToken(operator, is_operator=True))
                remaining = remaining[operator_match.end() :]
                continue

            # Extract next word (no parentheses in the word pattern)
            word_match = re.match(r"([^\s()]+)", remaining)
            if word_match:
                word = word_match.group(1)
                tokens.append(QueryToken(word, field=current_field, is_phrase=False))
                remaining = remaining[word_match.end() :]
                current_field = None
                continue

            # Shouldn't reach here
            break

        return tokens

    def validate(self, tokens: List[QueryToken]) -> bool:
        """Validate parsed tokens for correctness.

        Args:
            tokens: List of tokens to validate

        Returns:
            True if valid, False otherwise
        """
        if not tokens:
            return False

        # Check for balanced parentheses
        paren_count = 0
        for token in tokens:
            if token.value == "(":
                paren_count += 1
            elif token.value == ")":
                paren_count -= 1
            if paren_count < 0:
                return False

        if paren_count != 0:
            logger.warning("Unbalanced parentheses in query")
            return False

        return True


class BaseQueryTranslator(ABC):
    """Abstract base class for provider-specific query translators.

    Subclasses must implement provider-specific translation logic.
    """

    def __init__(self) -> None:
        """Initialize the translator."""
        self.parser = QueryParser()

    @abstractmethod
    def translate(self, query: Query) -> Dict[str, Any]:
        """Translate Query to provider-specific parameters.

        Args:
            query: Generic query object

        Returns:
            Dictionary of provider-specific parameters
        """
        pass

    @abstractmethod
    def translate_field(self, field: QueryField) -> str:
        """Translate standard field to provider-specific field name.

        Args:
            field: Standard field

        Returns:
            Provider-specific field name
        """
        pass

    @abstractmethod
    def translate_operator(self, operator: str) -> str:
        """Translate Boolean operator to provider syntax.

        Args:
            operator: Standard operator (AND, OR, NOT)

        Returns:
            Provider-specific operator syntax
        """
        pass

    def build_filter_params(self, query: Query) -> Dict[str, Any]:
        """Build common filter parameters.

        Args:
            query: Query object

        Returns:
            Dictionary of filter parameters
        """
        params: Dict[str, Any] = {}

        if query.year_min is not None:
            params["year_min"] = query.year_min

        if query.year_max is not None:
            params["year_max"] = query.year_max

        if query.language:
            params["language"] = query.language

        return params

    def extract_field_queries(self, tokens: List[QueryToken]) -> Dict[QueryField, List[str]]:
        """Extract terms grouped by field.

        Args:
            tokens: Parsed query tokens

        Returns:
            Dictionary mapping fields to terms
        """
        field_queries: Dict[QueryField, List[str]] = {}

        for token in tokens:
            if not token.is_operator and token.field is not None:
                if token.field not in field_queries:
                    field_queries[token.field] = []
                field_queries[token.field].append(token.value)

        return field_queries

    def escape_special_chars(self, text: str, special_chars: str = "") -> str:
        """Escape special characters for provider.

        Args:
            text: Text to escape
            special_chars: String of characters to escape

        Returns:
            Escaped text
        """
        if not special_chars:
            return text

        escaped = text
        for char in special_chars:
            escaped = escaped.replace(char, f"\\{char}")

        return escaped


class SimpleQueryTranslator(BaseQueryTranslator):
    """Simple query translator for basic text search.

    Suitable for providers that only support simple text queries
    without field-specific search or Boolean operators.
    """

    def __init__(self, field_map: Optional[Dict[QueryField, str]] = None):
        """Initialize simple translator.

        Args:
            field_map: Optional mapping of QueryField to provider field names
        """
        super().__init__()
        self.field_map = field_map or {}

    def translate(self, query: Query) -> Dict[str, Any]:
        """Translate to simple text search.

        Args:
            query: Query object

        Returns:
            Dictionary with 'q' key for query text
        """
        params = {"q": query.text}
        params.update(self.build_filter_params(query))
        return params

    def translate_field(self, field: QueryField) -> str:
        """Get provider field name."""
        return self.field_map.get(field, field.value)

    def translate_operator(self, operator: str) -> str:
        """Return operator as-is (not supported)."""
        return operator


class BooleanQueryTranslator(BaseQueryTranslator):
    """Advanced query translator with Boolean operator support.

    Supports field-specific queries and Boolean operators.
    Providers can customize operator syntax and field names.
    """

    def __init__(
        self,
        field_map: Dict[QueryField, str],
        operator_map: Optional[Dict[str, str]] = None,
        special_chars: str = "",
    ):
        """Initialize Boolean translator.

        Args:
            field_map: Mapping of QueryField to provider field names
            operator_map: Mapping of operators to provider syntax
            special_chars: Characters to escape in queries
        """
        super().__init__()
        self.field_map = field_map
        self.operator_map = operator_map or {
            "AND": "AND",
            "OR": "OR",
            "NOT": "NOT",
        }
        self.special_chars = special_chars

    def translate(self, query: Query) -> Dict[str, Any]:
        """Translate to Boolean query.

        Args:
            query: Query object

        Returns:
            Dictionary with translated query
        """
        # Parse query
        tokens = self.parser.parse(query.text)

        # Validate
        if not self.parser.validate(tokens):
            logger.warning("Invalid query, using as simple text")
            return {"q": query.text}

        # Build query string
        query_parts = []
        for token in tokens:
            if token.is_operator:
                # Translate operator
                if token.value in self.operator_map:
                    query_parts.append(self.operator_map[token.value])
                else:
                    query_parts.append(token.value)
            else:
                # Translate field and term
                field = self.translate_field(token.field)
                term = self.escape_special_chars(token.value, self.special_chars)

                if token.is_phrase:
                    query_parts.append(f'{field}:"{term}"')
                else:
                    query_parts.append(f"{field}:{term}")

        translated_query = " ".join(query_parts)

        params = {"q": translated_query}
        params.update(self.build_filter_params(query))

        return params

    def translate_field(self, field: QueryField) -> str:
        """Translate field to provider name."""
        return self.field_map.get(field, field.value)

    def translate_operator(self, operator: str) -> str:
        """Translate operator to provider syntax."""
        return self.operator_map.get(operator, operator)


class StructuredQueryTranslator(BaseQueryTranslator):
    """Translator for structured query APIs.

    For providers that use structured query formats (JSON, dicts)
    rather than query strings.
    """

    def __init__(self, field_map: Dict[QueryField, str]):
        """Initialize structured translator.

        Args:
            field_map: Mapping of QueryField to provider field names
        """
        super().__init__()
        self.field_map = field_map

    def translate(self, query: Query) -> Dict[str, Any]:
        """Translate to structured query format.

        Args:
            query: Query object

        Returns:
            Nested dictionary representing structured query
        """
        # Parse query
        tokens = self.parser.parse(query.text)

        # Group by field
        field_queries = self.extract_field_queries(tokens)

        # Build structured query
        query_dict: Dict[str, Any] = {}
        for field, terms in field_queries.items():
            provider_field = self.translate_field(field)
            if len(terms) == 1:
                query_dict[provider_field] = terms[0]
            else:
                query_dict[provider_field] = {"$or": terms}

        # Add filters
        filters = self.build_filter_params(query)
        if filters:
            query_dict["filters"] = filters

        return query_dict

    def translate_field(self, field: QueryField) -> str:
        """Translate field to provider name."""
        return self.field_map.get(field, field.value)

    def translate_operator(self, operator: str) -> str:
        """Translate operator to structured format."""
        operator_map = {
            "AND": "$and",
            "OR": "$or",
            "NOT": "$not",
        }
        return operator_map.get(operator, operator)


def create_translator(
    style: str, field_map: Optional[Dict[QueryField, str]] = None, **kwargs: Any
) -> BaseQueryTranslator:
    """Factory function to create query translators.

    Args:
        style: Translator style ('simple', 'boolean', 'structured')
        field_map: Field mapping for the provider
        **kwargs: Additional arguments for translator

    Returns:
        Appropriate translator instance

    Example:
        >>> translator = create_translator(
        ...     'boolean',
        ...     field_map={QueryField.TITLE: 'ti'},
        ...     operator_map={'AND': '&&'}
        ... )
    """
    field_map = field_map or {}

    if style == "simple":
        return SimpleQueryTranslator(field_map)
    elif style == "boolean":
        return BooleanQueryTranslator(field_map, **kwargs)
    elif style == "structured":
        return StructuredQueryTranslator(field_map)
    else:
        raise ValueError(f"Unknown translator style: {style}")
