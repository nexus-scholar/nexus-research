from typing import List, Optional
from pydantic import BaseModel, Field

class PaperAnalysis(BaseModel):
    """Structured analysis extracted from a single research paper."""
    
    # Core Metadata
    research_focus: str = Field(..., description="Main problem addressed (e.g., 'Tomato Leaf Disease Detection', 'Domain Adaptation').")
    
    # Technical Details
    models_used: List[str] = Field(..., description="List of specific architectures used (e.g., ['MobileNetV3', 'YOLOv8']).")
    datasets: List[str] = Field(..., description="Datasets used (e.g., ['PlantVillage', 'Custom Field Dataset']).")
    hardware: Optional[str] = Field(None, description="Hardware used for training/inference (e.g., 'NVIDIA RTX 3090', 'Raspberry Pi 4').")
    
    # Performance
    best_accuracy: Optional[str] = Field(None, description="Best reported accuracy or mAP (e.g., '98.5%').")
    
    # Qualitative
    key_contribution: str = Field(..., description="The single most important contribution of this paper.")
    limitations: List[str] = Field(..., description="Limitations or future work mentioned by authors.")
    
    # Categorization
    category: str = Field(..., description="Broad category: 'Architecture', 'Data-Centric', 'Deployment', 'Survey'.")
