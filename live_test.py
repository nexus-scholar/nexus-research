import os
import subprocess
import time
import json
from pathlib import Path

def run_command(command):
    print(f"Executing: {' '.join(command)}")
    # Force UTF-8 encoding for subprocess and rich
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    
    start = time.time()
    result = subprocess.run(command, capture_output=True, text=True, shell=True, env=env, encoding="utf-8")
    duration = time.time() - start
    
    if result.returncode != 0:
        print(f"Command failed with exit code {result.returncode}")
        # print(f"STDOUT: {result.stdout}")
        # print(f"STDERR: {result.stderr}")
    return result, duration

def main():
    log_file = Path("results.log")
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("=== NEXUS FULL PIPELINE LIVE TEST ===\n")
        f.write(f"Start Time: {time.ctime()}\n\n")

    metrics = {
        "performance": {},
        "coverage": {}
    }

    # 1. SEARCH
    # Using 1 result for speed in live test
    cmd = ["uv", "run", "nexus", "search", "--queries", "queries.yml", "--max-results", "1"]
    res, dur = run_command(cmd)
    metrics["performance"]["search"] = f"{dur:.2f}s"
    
    time.sleep(1) # FS sync
    runs = sorted(list(Path("results/outputs").glob("run_*")))
    if runs:
        latest_run = runs[-1]
        meta_path = latest_run / "metadata.json"
        if meta_path.exists():
            try:
                with open(meta_path, "r", encoding="utf-8") as m:
                    meta = json.load(m)
                    total_docs = sum(meta["results"].values())
                metrics["coverage"]["raw_retrieved"] = total_docs
            except:
                metrics["coverage"]["raw_retrieved"] = "ERROR: JSON parse"
        else:
            metrics["coverage"]["raw_retrieved"] = "ERROR: No metadata"
    else:
        metrics["coverage"]["raw_retrieved"] = "ERROR: No run dir"

    # 2. DEDUPLICATE
    if runs:
        cmd = ["uv", "run", "nexus", "deduplicate", "--input", str(latest_run)]
        res, dur = run_command(cmd)
        metrics["performance"]["dedup"] = f"{dur:.2f}s"
        
        time.sleep(1) # FS sync
        dedups = sorted(list(Path("results/dedup").glob("dedup_*")))
        if dedups:
            latest_dedup = dedups[-1]
            prisma_path = latest_dedup / "prisma_counts.json"
            if prisma_path.exists():
                try:
                    with open(prisma_path, "r", encoding="utf-8") as m:
                        prisma = json.load(m)
                        unique_count = prisma["screening"]["records_after_deduplication"]
                    metrics["coverage"]["unique_docs"] = unique_count
                except:
                    metrics["coverage"]["unique_docs"] = "ERROR: JSON parse"
            else:
                metrics["coverage"]["unique_docs"] = "ERROR: No prisma counts"
        else:
            metrics["coverage"]["unique_docs"] = "ERROR: No dedup dir"
    else:
        metrics["performance"]["dedup"] = "SKIPPED"

    # 3. SCREEN (Optional)
    if os.getenv("OPENAI_API_KEY"):
        cmd = ["uv", "run", "nexus", "screen", "--limit", "1"]
        res, dur = run_command(cmd)
        metrics["performance"]["screening"] = f"{dur:.2f}s"
    else:
        metrics["performance"]["screening"] = "SKIPPED (No API Key)"

    # 4. FETCH
    cmd = ["uv", "run", "nexus", "fetch", "--limit", "1"]
    res, dur = run_command(cmd)
    metrics["performance"]["fetch"] = f"{dur:.2f}s"
    
    pdfs = list(Path("results/pdfs").glob("*.pdf"))
    metrics["coverage"]["pdfs_downloaded"] = len(pdfs)

    # 5. EXTRACT
    cmd = ["uv", "run", "nexus", "extract", "--limit", "1"]
    res, dur = run_command(cmd)
    metrics["performance"]["extract"] = f"{dur:.2f}s"
    
    extractions = list(Path("results/extraction").glob("*"))
    metrics["coverage"]["extracted_folders"] = len(extractions)

    # Final Report
    with open(log_file, "a", encoding="utf-8") as f:
        f.write("\n=== PERFORMANCE METRICS ===\n")
        f.write(json.dumps(metrics["performance"], indent=2))
        f.write("\n\n=== COVERAGE METRICS ===\n")
        f.write(json.dumps(metrics["coverage"], indent=2))
        f.write(f"\n\nTest Completed: {time.ctime()}\n")

    print(f"\nFull test complete. Results persistent in {log_file}")

if __name__ == "__main__":
    main()
