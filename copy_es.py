"""Copy public-memory_units from Boombox ES to local ES for Domu testing."""
from elasticsearch import Elasticsearch
from elasticsearch.helpers import scan, bulk
import json, sys

remote = Elasticsearch("http://192.168.1.110:9200")
local = Elasticsearch("http://127.0.0.1:9200")

# Get mapping from remote
mapping = remote.indices.get_mapping(index="public-memory_units")
print(f"Mapping retrieved for index: {list(mapping.keys())}", flush=True)

# Create local index with same mapping
mapping_body = list(mapping.values())[0]
try:
    local.indices.create(index="public-memory_units", body=mapping_body)
    print("Local index created", flush=True)
except Exception as e:
    if "already exists" in str(e).lower() or "resource_already_exists" in str(e).lower():
        print("Local index already exists", flush=True)
    else:
        print(f"Warning creating index: {e}", flush=True)

# Copy documents
def generate_docs():
    for i, doc in enumerate(scan(remote, index="public-memory_units", query={"query": {"match_all": {}}})):
        source = doc["_source"]
        yield {
            "_index": "public-memory_units",
            "_id": doc["_id"],
            "_source": source
        }
        if i % 100 == 0:
            print(f"Scanning doc {i}...", flush=True)

success, errors = bulk(local, generate_docs(), chunk_size=200, raise_on_error=False)
print(f"\nCopied: {success} docs, errors: {len(errors)}", flush=True)
if errors:
    print(f"First error: {errors[0]}", flush=True)

# Verify
count = local.count(index="public-memory_units")
print(f"Local ES now has: {count['count']} docs in public-memory_units", flush=True)
