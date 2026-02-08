import json
import csv
from pathlib import Path
import re

def normalize_doi(doi):
    if not doi:
        return None
    v = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
    v = re.sub(r"^doi:\s*", "", v, flags=re.IGNORECASE)
    v = v.strip().lower()
    return v.replace("/", "_").replace(":", "_")

def get_ieee_arnumber(doc):
    # 1. From provider_id (If it's an IEEE result)
    if doc.get("provider") == "ieee" and doc.get("provider_id"):
        return doc["provider_id"]
    
    # 2. From URL
    url = doc.get("url") or ""
    match = re.search(r"document/(\d+)", url)
    if match:
        return match.group(1)
    
    return None

input_file = Path("results/ranked/q1_papers_final_screened_dataset.jsonl")
pdf_dir = Path("data/pdfs")
output_csv = Path("results/missing_pdfs_for_sndl.csv")

missing_papers = []

with open(input_file, "r", encoding="utf-8") as f:
    for line in f:
        doc = json.loads(line)
        doi = doc.get("external_ids", {}).get("doi")
        arxiv_id = doc.get("external_ids", {}).get("arxiv_id")
        title = doc.get("title")
        url = doc.get("url")
        
        filename = None
        if doi:
            norm = normalize_doi(doi)
            filename = f"{norm}.pdf"
        elif arxiv_id:
            filename = f"arxiv_{arxiv_id}.pdf"
        else:
            filename = f"doc_{abs(hash(title))}.pdf"
            
        if not (pdf_dir / filename).exists():
            # Construct SNDL Proxy URL for IEEE
            sndl_url = ""
            arnumber = get_ieee_arnumber(doc)
            if arnumber:
                sndl_url = f"https://ieeexplore-ieee-org.www.sndl1.arn.dz/stamp/stamp.jsp?tp=&arnumber={arnumber}"
            
            missing_papers.append({
                "title": title,
                "provider": doc.get("provider", "unknown"),
                "url": url,
                "sndl_proxy_url": sndl_url,
                "doi": doi,
                "expected_filename": filename
            })

with open(output_csv, "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["title", "provider", "url", "sndl_proxy_url", "doi", "expected_filename"])
    writer.writeheader()
    writer.writerows(missing_papers)

print(f"Successfully identified {len(missing_papers)} missing PDFs.")
print(f"Added SNDL proxy URLs for IEEE papers.")
print(f"List saved to: {output_csv}")