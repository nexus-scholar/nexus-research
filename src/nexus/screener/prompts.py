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

# ---------------------------------------------------------------------------
# Layered screening prompts
#
# The layered screening strategy uses three successive LLM calls to
# progressively narrow down the set of candidate documents. Each layer
# has its own system prompt describing what to look for and a user
# prompt supplying the paper details.

def build_layer1_system_prompt() -> str:
    """System prompt for Layer 1: check for visual deep-learning plant disease work."""
    return (
        "You are screening papers for a systematic review on image-based "
        "deep learning for plant/leaf disease diagnosis.\n"
        "Your goal is to decide whether a paper uses visual data of plants "
        "or leaves, applies deep-learning or computer-vision techniques "
        "(e.g., CNNs, transformers, YOLO, EfficientNet), and focuses on "
        "plant or leaf diseases (not weeds, insects, nutrient deficiency, "
        "remote sensing or hyperspectral-only studies).\n"
        "Respond strictly with 'include', 'exclude' or 'maybe' and a one-"
        "sentence rationale."
    )


def build_layer2_system_prompt() -> str:
    """System prompt for Layer 2: check crop species and domain relevance."""
    return (
        "You are screening papers that already passed the first layer of "
        "visual deep-learning relevance. Now determine whether the "
        "disease affects crops or leaves (e.g. tomato, rice, wheat, grapes, "
        "apples), the imaging is at the leaf or plant level (field or lab) "
        "and not aerial remote sensing, hyperspectral, or thermal-only. Also "
        "check whether the study uses benchmark plant-disease datasets (e.g. "
        "PlantVillage, PlantDoc, PlantWild) or their own leaf images.\n"
        "Return 'include', 'exclude' or 'maybe' with a brief reason."
    )


def build_layer3_system_prompt() -> str:
    """System prompt for Layer 3: assess method and thematic contribution."""
    return (
        "You are screening papers that already passed earlier relevance layers. "
        "Confirm that the paper is an empirical study (not just a review) and "
        "addresses at least one of the following themes: domain shift/"
        "generalisation; lightweight/edge or mobile deployment; model compression/pruning; "
        "self-/semi-/few-shot or meta-learning; generative augmentation (GANs, "
        "diffusion); active learning or other data-centric methods; multimodal "
        "sensor fusion (e.g. RGB+thermal); disease severity estimation/monitoring. "
        "Ensure that it reports performance metrics or implementation results.\n"
        "Respond with 'include', 'exclude' or 'maybe' and provide a one-line rationale."
    )


def build_layer_user_prompt(title: str, abstract: str) -> str:
    """User prompt used for all layers."""
    return f"Title: {title}\nAbstract: {abstract or 'No abstract available.'}"

