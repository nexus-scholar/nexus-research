import json
from pathlib import Path

# Path to your latest screening results
input_file = Path("results/screening/screening_dedup_2026-02-01_164642.jsonl")
output_file = Path("results/screening/recovery_candidates.jsonl")

recovered_count = 0

with open(input_file, "r", encoding="utf-8") as f, \
     open(output_file, "w", encoding="utf-8") as out:
    for line in f:
        doc = json.loads(line)
        # Check if it was excluded by the "pest" heuristic
        reason = doc.get("screening_reason", "").lower()
        if doc.get("decision") == "exclude" and "pest" in reason:
            # Clear previous screening metadata so the screener processes it fresh
            doc["decision"] = None
            doc["screening_reason"] = None
            doc["screening_confidence"] = None
            doc["screening_layers"] = []
            
            out.write(json.dumps(doc) + "\n")
            recovered_count += 1

print(f"Successfully identified {recovered_count} papers for recovery pass.")
print(f"Candidates saved to: {output_file}")

