import logging
from typing import Iterator, List

from nexus.core.config import ScreenerConfig
from nexus.core.models import Document
from nexus.screener.client import LLMClient
from nexus.screener.models import ScreeningDecision, ScreeningResult
from nexus.screener.prompts import build_screening_system_prompt, build_paper_user_prompt

logger = logging.getLogger(__name__)

class Screener:
    """Main screener logic."""

    def __init__(self, client: LLMClient = None):
        self.client = client or LLMClient()

    def screen_documents(self, documents: List[Document], criteria: str = "General Relevance") -> Iterator[ScreeningResult]:
        """Screen a list of documents against criteria."""
        
        system_prompt = build_screening_system_prompt(criteria)

        for doc in documents:
            try:
                user_prompt = build_paper_user_prompt(
                    title=doc.title,
                    abstract=doc.abstract or "No abstract available.",
                    query_context=doc.query_text or "General"
                )

                result = self.client.screen_paper(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_model=ScreeningResult
                )
                
                # Hydrate result with doc info
                result.doi = doc.external_ids.doi
                result.title = doc.title
                
                yield result

            except Exception as e:
                logger.error(f"Failed to screen {doc.title[:30]}...: {e}")
                # Yield error result? Or skip. 
                # Better to return a 'maybe' with error reasoning so we don't lose it.
                yield ScreeningResult(
                    doi=doc.external_ids.doi,
                    title=doc.title,
                    decision=ScreeningDecision.MAYBE,
                    confidence=0,
                    reasoning=f"LLM Error: {str(e)}"
                )

# ---------------------------------------------------------------------------
# Layered screener implementation
#
class LayeredScreener:
    """Multi-stage screener implementing a layered screening strategy.

    The layered screener performs three successive LLM calls on each
    document. Each layer uses a distinct system prompt to check for a
    specific set of inclusion criteria. If a paper fails a layer (i.e.,
    is marked 'exclude'), subsequent layers are skipped. The final
    decision is determined by the first exclusion or by the presence of
    any 'maybe' decisions. Reasons from each layer are concatenated to
    provide a transparent audit trail.

    Attributes
    ----------
    client : LLMClient
        Client used to perform LLM calls.
    models : List[str]
        Names of models to use for each layer. If fewer than three are
        provided, the last model is reused for remaining layers.
    include_patterns : List[str]
        Simple keywords that must be present in the document (used by
        heuristics filter).
    exclude_patterns : List[str]
        Simple keywords that must not be present in the document.
    """

    def __init__(
        self,
        client: LLMClient | None = None,
        models: List[str] | None = None,
        include_patterns: List[str] | None = None,
        include_groups: List[List[str]] | None = None,
        exclude_patterns: List[str] | None = None,
        config: ScreenerConfig | None = None,
    ) -> None:
        self.client = client or LLMClient()
        screener_config = config or ScreenerConfig()
        
        # Determine models to use, ensuring at least one model exists.
        if models:
            self.models = models
        elif screener_config.models:
            self.models = screener_config.models
        else:
            self.models = [self.client.model] * 3
            
        # Heuristic filters configured via YAML.
        if include_patterns is None:
            self.include_patterns = screener_config.include_patterns
        else:
            self.include_patterns = include_patterns
        if include_groups is None:
            self.include_groups = screener_config.include_groups
        else:
            self.include_groups = include_groups
        if exclude_patterns is None:
            self.exclude_patterns = screener_config.exclude_patterns
        else:
            self.exclude_patterns = exclude_patterns

    def screen_documents(self, documents: List[Document]) -> Iterator[ScreeningResult]:
        """Screen documents using heuristics and layered LLM prompts."""
        # Import here to avoid circular imports.
        from nexus.screener.prompts import (
            build_layer1_system_prompt,
            build_layer2_system_prompt,
            build_layer3_system_prompt,
            build_layer_user_prompt,
        )
        from nexus.screener.heuristics import filter_documents

        # Get the list of documents that pass heuristics.
        # We need to know which ones passed to handle those that didn't.
        # However, filter_documents returns an iterator. 
        # For simplicity and to maintain 1:1, we'll re-implement the loop here 
        # or use a helper that doesn't just drop papers.
        
        # We'll re-use the patterns from self to check each doc manually
        from nexus.screener.heuristics import _textify
        import re
        
        includes = [re.compile(p, re.IGNORECASE) for p in (self.include_patterns or [])]
        excludes = [re.compile(p, re.IGNORECASE) for p in (self.exclude_patterns or [])]
        group_patterns = []
        if self.include_groups:
            group_patterns = [[re.compile(p, re.IGNORECASE) for p in group] for group in self.include_groups]

        for doc in documents:
            text = _textify(doc)
            failed_heuristic = False
            heuristic_reason = ""

            # Check exclude patterns first
            for p in excludes:
                if p.search(text):
                    failed_heuristic = True
                    heuristic_reason = f"Excluded by heuristic pattern: '{p.pattern}'"
                    break
            
            if not failed_heuristic:
                if group_patterns:
                    for idx, group in enumerate(group_patterns):
                        if not any(p.search(text) for p in group):
                            failed_heuristic = True
                            heuristic_reason = f"Failed heuristic include group {idx+1}"
                            break
                elif includes:
                    if not any(p.search(text) for p in includes):
                        failed_heuristic = True
                        heuristic_reason = "Failed all heuristic include patterns"

            if failed_heuristic:
                yield ScreeningResult(
                    doi=doc.external_ids.doi,
                    title=doc.title,
                    decision=ScreeningDecision.EXCLUDE,
                    confidence=100,
                    reasoning=heuristic_reason,
                    tags=["heuristic_exclusion"]
                )
                continue

            # If it passed heuristics, proceed to layered LLM screening
            title = doc.title or ""
            abstract = doc.abstract or ""
            user_prompt = build_layer_user_prompt(title=title, abstract=abstract)
            reasons: List[str] = []
            final_decision = ScreeningDecision.INCLUDE
            final_confidence = 100

            system_prompts = [
                build_layer1_system_prompt(),
                build_layer2_system_prompt(),
                build_layer3_system_prompt(),
            ]
            for layer_idx, system_prompt in enumerate(system_prompts):
                model_name = self.models[min(layer_idx, len(self.models) - 1)]
                prev_model = self.client.model
                self.client.model = model_name
                try:
                    result = self.client.screen_paper(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        response_model=ScreeningResult,
                    )
                finally:
                    self.client.model = prev_model
                
                reasons.append(result.reasoning)
                if result.decision == ScreeningDecision.EXCLUDE:
                    final_decision = ScreeningDecision.EXCLUDE
                    final_confidence = min(final_confidence, result.confidence)
                    break
                if result.decision == ScreeningDecision.MAYBE:
                    final_decision = ScreeningDecision.MAYBE
                final_confidence = min(final_confidence, result.confidence)

            yield ScreeningResult(
                doi=doc.external_ids.doi,
                title=doc.title,
                decision=final_decision,
                confidence=final_confidence,
                reasoning=" | ".join(reasons),
                tags=[],
            )
