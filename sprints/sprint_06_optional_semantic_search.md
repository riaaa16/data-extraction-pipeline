# Sprint 06 (Optional): Semantic Search & Theme Assignment

## Goal
Enable semantic retrieval over entries and support more consistent theme assignment using embeddings.

## Scope
- Build an embedding index for `raw_text` (and optionally selected fields)
- Provide a programmatic search API (query → top-k entries)
- Provide optional helper utilities to assist theme assignment (e.g., nearest-neighbor grouping)

## Non-goals (explicitly out of scope)
- New UI screens beyond the existing workflow
- Complex vector databases; keep it local and lightweight

## Deliverables
- An embeddings module using `sentence-transformers` (optional dependency)
- A local in-memory index (or simple persisted file) of entry embeddings
- A search function:
  - `semantic_search(query, entries, k=10) -> list[entry]`
- A simple theme-assignment helper that can:
  - suggest similar entries for a given theme label, or
  - cluster entries into a small number of groups (lightweight)

## Implementation Tasks
1. **Embedding generation**
   - Choose a small, widely-available sentence-transformer model.
   - Generate embeddings for each entry’s `raw_text`.

2. **Indexing + retrieval**
   - Implement cosine similarity search (NumPy / sklearn) over embeddings.
   - Keep performance acceptable for typical UX datasets (hundreds to low thousands of entries).

3. **Optional theme assistance**
   - Implement a helper to group similar entries (kNN-based) to support consistent theme labeling.
   - Keep outputs interpretable (e.g., show exemplar entries per group).

4. **Integration surface**
   - Expose the semantic search and grouping utilities as callable functions for later UI integration (if desired).

## Acceptance Criteria
- Given a dataset with `N >= 10` entries, a query returns `k` results ranked by similarity.
- Results are stable (same query + same entries → same ordering).
- The feature remains optional: the app can run without embeddings installed.
