import logging
from typing import Iterator, List

from nexus.core.models import Document
from nexus.screener.client import LLMClient
from nexus.screener.models import ScreeningResult
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
                    decision=ScreeningResult.decision.MAYBE,
                    confidence=0,
                    reasoning=f"LLM Error: {str(e)}"
                )
