import json
from pathlib import Path

original_file = Path("results/screening/screening_dedup_2026-02-01_164642.jsonl")
recovery_file = Path("results/screening/screening_screening.jsonl")
output_file = Path("results/screening/final_screened_dataset.jsonl")

# 1. Load recovery results into a map for quick overwrite
updates = {}
if recovery_file.exists():
    with open(recovery_file, "r", encoding="utf-8") as f:
        for line in f:
            doc = json.loads(line)
            # Use title as reliable key for this internal merge
            key = doc.get("title", "").lower().strip()
            updates[key] = doc

# 2. Merge and Save
final_docs = []
counts = {"include": 0, "maybe": 0, "exclude": 0}

with open(original_file, "r", encoding="utf-8") as f:
    for line in f:
        doc = json.loads(line)
        key = doc.get("title", "").lower().strip()
        
        # If we have a fresh decision from the recovery pass, use it
        if key in updates:
            doc = updates[key]
        
        final_docs.append(doc)
        counts[doc.get("decision", "exclude")] += 1

with open(output_file, "w", encoding="utf-8") as out:
    for doc in final_docs:
        out.write(json.dumps(doc) + "\n")

print("Merge Complete!")
print(f"Final Path: {output_file}")
print(f"Total Papers: {len(final_docs)}")
print(f"  - INCLUDE: {counts['include']}")
print(f"  - MAYBE:   {counts['maybe']}")
print(f"  - EXCLUDE: {counts['exclude']}")
