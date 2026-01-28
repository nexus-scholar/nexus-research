"""
Prompts for the LLM Screener.
"""

def build_screening_system_prompt(criteria: str) -> str:
    """Build the system prompt with specific screening criteria."""
    return f"""You are an expert research assistant screening scientific papers for a systematic literature review.

Your goal is to evaluate if a paper is relevant based on the provided inclusion/exclusion criteria.

CRITERIA:
{criteria}

INSTRUCTIONS:
1. Analyze the Title and Abstract.
2. Determine if the paper meets the criteria.
3. Be strict but fair. If the abstract is ambiguous, mark as 'maybe'.
4. Provide a confidence score (0-100).
5. Provide a brief, one-sentence reasoning for your decision.
"""

def build_paper_user_prompt(title: str, abstract: str, query_context: str = "") -> str:
    """Build the user prompt for a specific paper."""
    prompt = f"""Please screen this paper:

Title: {title}
"""
    if query_context:
        prompt += f"Context/Theme: {query_context}\n"
        
    prompt += f"\nAbstract:\n{abstract}"
    return prompt

