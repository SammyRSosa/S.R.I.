import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from database.store import DocumentStore

store = DocumentStore()

# Find and remove crawled garbage documents
bad_ids = []
for doc_id, doc in store.documents.items():
    title = doc.get("title", "")
    if "[Crawled]" in title:
        print(f"  CRAWLED doc_id={doc_id}: {title}")
        # Check if it's garbage
        if any(kw in title.lower() for kw in ["kbbq", "merriam", "dictionary", "korean won", "south korean"]):
            bad_ids.append(doc_id)
            print(f"    → REMOVING (garbage)")

if bad_ids:
    for did in bad_ids:
        del store.documents[did]
    store.save()
    print(f"\nRemoved {len(bad_ids)} garbage documents. Corpus now: {len(store.documents)}")
else:
    print("\nNo garbage documents found.")
