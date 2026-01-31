import json
import logging
from pathlib import Path
from typing import Optional

from nexus.analysis.models import PaperAnalysis
from nexus.screener.client import LLMClient

logger = logging.getLogger(__name__)

class AnalysisEngine:
    def __init__(self, model: str = "google/gemini-2.0-flash-001"):
        self.client = LLMClient(model=model)

    def analyze_markdown(self, md_path: Path) -> Optional[PaperAnalysis]:
        """
        Analyze a markdown file and return structured insights.
        """
        if not md_path.exists():
            return None

        # Read content (Truncate to ~50k chars to be safe/fast, or rely on model capacity)
        # Gemini Flash has huge context, so 100k chars is fine.
        text = md_path.read_text(encoding="utf-8")
        if len(text) > 100000:
            text = text[:100000] + "\n...(truncated)..."

        system_prompt = """
You are a senior computer science researcher conducting a Systematic Literature Review.
Analyze the provided research paper text and extract structured data.

Be precise. For lists (models, datasets), return clean names (e.g., "YOLOv8" not "YOLOv8 model").
"""

        user_prompt = f"Analyze this paper:\n\n{text}"

        try:
            # Re-use the client's screen_paper method logic but we need to implement a generic structured call
            # The client currently has 'screen_paper', let's access the client directly or add a new method?
            # I'll rely on the fact that LLMClient wraps the OpenAI client which supports 'parse'
            
            completion = self.client.client.beta.chat.completions.parse(
                model=self.client.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format=PaperAnalysis,
            )
            return completion.choices[0].message.parsed

        except Exception as e:
            logger.error(f"Analysis failed for {md_path.name}: {e}")
            return None
