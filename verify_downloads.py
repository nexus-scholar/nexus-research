import os
import shutil
import csv
from pathlib import Path

csv_path = Path("results/missing_pdfs_for_sndl.csv")
downloaded_dir = Path("results/missing_pdfs")
target_dir = Path("data/pdfs")

target_dir.mkdir(parents=True, exist_ok=True)

# 1. Read expected filenames from CSV
expected_files = set()
with open(csv_path, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        expected_files.add(row["expected_filename"].strip())

# 2. Get list of downloaded files (handle potential trailing spaces)
original_names = {f.name: f.name.strip() for f in downloaded_dir.iterdir() if f.is_file()}
downloaded_stripped = set(original_names.values())

# 3. Compare and Move
success_count = 0
not_found = []

for filename in expected_files:
    if filename in downloaded_stripped:
        # Find the original name (with potential spaces)
        orig_name = [k for k, v in original_names.items() if v == filename][0]
        # Move and rename to the correct clean name
        shutil.move(downloaded_dir / orig_name, target_dir / filename)
        success_count += 1
    else:
        not_found.append(filename)

# 4. Check for extra files (incorrect names)
extra_files = downloaded_stripped - expected_files

print(f"Verified and moved {success_count} PDFs to {target_dir}")
print(f"Missing from downloads: {len(not_found)}")
for f in not_found:
    print(f"  - {f}")

if extra_files:
    print(f"Extra files found (names don't match CSV): {len(extra_files)}")
    for f in extra_files:
        print(f"  - {f}")
