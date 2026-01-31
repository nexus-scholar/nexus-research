import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import re

def clean_list_column(df, col):
    """Explode comma-separated strings into individual rows."""
    # Handle NaNs
    s = df[col].dropna().astype(str)
    # Split by comma
    s = s.str.split(', ')
    return s.explode()

def extract_accuracy(acc_str):
    """Extract numeric accuracy from string."""
    if not isinstance(acc_str, str):
        return None
    # Find percentage
    match = re.search(r'(\d{2,3}\.?\d*)%', acc_str)
    if match:
        try:
            val = float(match.group(1))
            if 50 <= val <= 100: # Sanity check
                return val
        except:
            pass
    return None

def generate_charts(input_csv: Path, output_dir: Path):
    """Generate analysis charts."""
    if not input_csv.exists():
        print(f"Error: {input_csv} not found.")
        return

    df = pd.read_csv(input_csv)
    output_dir.mkdir(exist_ok=True)
    
    sns.set_theme(style="whitegrid")

    # 1. Model Popularity
    plt.figure(figsize=(12, 8))
    models = clean_list_column(df, "models_used")
    # Normalize names (lowercase, strip)
    models = models.str.lower().str.strip()
    # Map common aliases (optional)
    top_models = models.value_counts().head(20)
    sns.barplot(x=top_models.values, y=top_models.index, hue=top_models.index, palette="viridis", legend=False)
    plt.title("Top 20 Architectures in Plant Disease Detection (2024-2025)")
    plt.xlabel("Count")
    plt.tight_layout()
    plt.savefig(output_dir / "models_distribution.png")
    plt.close()

    # 2. Dataset Usage
    plt.figure(figsize=(12, 8))
    datasets = clean_list_column(df, "datasets")
    datasets = datasets.str.strip()
    top_data = datasets.value_counts().head(15)
    sns.barplot(x=top_data.values, y=top_data.index, hue=top_data.index, palette="magma", legend=False)
    plt.title("Most Used Datasets")
    plt.xlabel("Count")
    plt.tight_layout()
    plt.savefig(output_dir / "datasets_distribution.png")
    plt.close()

    # 3. Accuracy Distribution
    # Extract year if possible (need year column in input CSV, but we didn't save it explicitly in analysis model)
    # The 'source' column might have year if filename has it? No.
    # But we can try to extract accuracy.
    df["numeric_acc"] = df["best_accuracy"].apply(extract_accuracy)
    
    if df["numeric_acc"].notna().sum() > 5:
        plt.figure(figsize=(8, 6))
        sns.boxplot(y=df["numeric_acc"], color="skyblue")
        plt.title("Distribution of Reported Accuracy")
        plt.ylabel("Accuracy (%)")
        plt.tight_layout()
        plt.savefig(output_dir / "accuracy_boxplot.png")
        plt.close()

    print(f"Charts generated in {output_dir}")
