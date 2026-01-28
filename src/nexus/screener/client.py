import json
import os
from typing import Any, Dict, Optional, Type

from openai import OpenAI
from pydantic import BaseModel

class LLMClient:
    """Wrapper for LLM interactions."""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: str = "gpt-4o"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("LLM_BASE_URL")
        self.model = model or os.getenv("LLM_MODEL", "gpt-4o")
        
        if not self.api_key:
            # Don't raise yet, allow lazy config
            pass

        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def screen_paper(self, system_prompt: str, user_prompt: str, response_model: Type[BaseModel]) -> BaseModel:
        """Send a screening request and parse structure."""
        if not self.api_key:
             raise ValueError("OpenAI API Key not found. Set OPENAI_API_KEY env var.")

        completion = self.client.beta.chat.completions.parse(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format=response_model,
        )

        return completion.choices[0].message.parsed
