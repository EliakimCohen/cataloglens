# Architecture and tradeoffs

```text
CSV / JSON feeds
       |
  file parsing              malformed file -> abort batch
       |
  row normalization         invalid row -> quarantine
       |
  merchant/SKU grouping     conflicting group -> quarantine all members
       |
  atomic SQLite snapshot ----------------------> literal SQL search
       |                                               |
  selected product                               read-only dashboard
       |
  optional Claude request
       |
  category + exact evidence validation
       |
  pending suggestion -> human decision -> category update with provenance
```

## Boundaries

`core.py` has no database or network dependency. It owns text normalization,
money parsing, the five category names and the fixed keyword baseline.

`store.py` parses files before entering the write transaction. It tracks one
accepted offer per merchant/SKU key and retains every conflicting occurrence in
the rejection table. A run is visible to search only after the complete import
transaction commits. Search always reads the newest run.

Each run records source filenames and SHA-256 hashes. Each accepted offer stores
its parsed source record, feed name and one-based logical record number. This is
not a physical CSV line number: quoted fields may span several lines. Repeated
identical offers retain the first record as their representative; the run tracks
the number of collapsed duplicates. Every previous source file is still required
for byte-for-byte reconstruction; the database stores parsed records and hashes,
not a byte archive of each feed.

`ai.py` sends title and description only. A bounded tool schema is requested, then
locally validated regardless of what the provider claims. Unrecognized fields,
unsupported categories, absent tool calls, truncated responses and invented
quotes fail closed. There are no provider-controlled tools to execute: the tool
call is a structured classification proposal. The model cannot issue SQL or
change a price.

The Messages API model is explicit configuration rather than a moving default.
The adapter uses API version `2026-10-21` and `tool_choice: auto`; a model that
returns prose instead of a tool call yields a validation error. Authentication,
rate-limit and transport failures do not silently fall back to rules and are
not retried. Production workloads would need a rate-limited job queue, idempotent
requests and explicit retry/cost policies.

`review` is a local human operation. Approval changes only category/evidence and
records the model as the source of the reviewed label. Other pending suggestions
for the product are rejected, preventing an older proposal from being approved
after a newer decision. The original feed record remains unchanged. This is a
single-user tool, not a multi-user audit system with authenticated reviewers.

`web.py` exposes search, import summaries, rule evaluation and review history. It
does not expose import, model execution or approval endpoints. Model credentials
never go to the browser. The built-in HTTP server is for local development only.

## Evaluation

The 24-case fixture is manually authored synthetic data with explicit category
labels. It includes ambiguity, accessories and instruction-like source text.
Neither rules nor optional Claude receive the expected labels. The baseline is
frozen at `keywords-v1`; it has known weaknesses and is not tuned to achieve a
headline score. The fixture is separate from demo feeds but shares vocabulary;
it is not an independent statistical holdout. No model was trained on it.

Accuracy counts exact category matches across all cases. Per-category precision
and recall use the usual confusion-matrix counts. An undefined denominator is
reported as `null`, not zero. `other_rate` is the proportion classified as `other`;
it is not a calibrated confidence or error rate. Model runs record token usage
and request time, while rule runs record zero tokens and do not benchmark latency.

## Deliberate omissions

There is no cross-merchant entity resolution, currency conversion, availability
verification, natural-language price parser, payment integration, credit scoring
or autonomous buying. A useful next experiment would be a larger independently
labeled product set, followed by a measured comparison of rules, a smaller local
classifier and a hosted LLM. A model should earn its added cost and complexity.
