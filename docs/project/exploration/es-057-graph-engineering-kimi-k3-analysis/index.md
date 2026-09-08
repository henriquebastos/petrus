---
code: ES-057
status: Completed
status_reason: >-
  The source audit and tool comparison distinguish knowledge/retrieval graphs
  from Petrus execution nets and support a bounded composition recommendation,
  not a kernel change, roadmap promotion, or provider support claim.
opened: 2026-08-18
related:
  - ES-056
  - CV16
  - docs/product/principles.md
  - docs/project/decisions/records/2026-07-23T0315Z-agent-context-and-verification-stay-concrete.md
  - docs/project/decisions/records/2026-08-05T0923Z-net-owned-pi-loop-mirrors-a-bounded-public-seam.md
source_context:
  - https://x.com/kirillk_web3/status/2087619214915826155
research_sources:
  - https://arxiv.org/abs/2404.16130
  - https://github.com/microsoft/graphrag
  - https://arxiv.org/abs/2510.26692
  - https://arxiv.org/abs/2607.24653
  - https://github.com/MoonshotAI/Kimi-K3
  - https://github.com/MoonshotAI/kimi-code
  - https://github.com/stanfordnlp/dspy
  - https://neo4j.com/docs/neo4j-graphrag-python/current/
  - https://arxiv.org/abs/2603.22528
---

# 1 Graph engineering and Kimi K3

## 1a Conclusion and research date

The completed inquiry treats graph-grounded answering as an application that
could run on Petrus. Knowledge and retrieval graphs keep their own semantics;
Petrus retains process identity, History, replay, and Activity acceptance.
No new dependency, Agenticus profile, or Delivery candidate was promoted.

The initiating article appeared on 2026-08-12; sources were checked on
2026-08-18. Frontmatter preserves the article and research URLs. The findings
below are that dated audit, not a claim about current model or project releases.
`[D]` marks checked sources, `[E]` inspected/executed repository evidence,
`[R]` unverified reports, and `[X]` claims refuted or narrowed by checked sources.
Petrus recommendations are explicitly inferences from that audit.

## 1b Distinct graph owners


| Structure | Nodes and edges mean | Correct owner | Not evidence of |
| --- | --- | --- | --- |
| Knowledge graph | Domain entities and asserted relationships, with sources and time | Application data store such as Neo4j | Execution order, retry, or recovery |
| Retrieval/index graph | Chunks, entities, communities, embeddings, and paths used to select context | GraphRAG/retrieval subsystem | Truth of the extracted relationships |
| Agent/tool loop | Model decisions and tool calls | Kimi Code or an Agenticus program, bounded by host authority | Durable business-process state by itself |
| Petrus execution net | Places, typed tokens, transitions, guards, timers, and Activity boundaries | Impetus Net + one Instance History | A general-purpose domain knowledge database |

`[D]` Microsoft GraphRAG describes itself as a pipeline and transformation suite
that extracts structured data from unstructured text. `[E]` Petrus defines the
durable thing as the Net Instance; marking plus one canonical History; and places
agents inside that Net as handler behavior. The shared word “graph” does not make
the models interchangeable.

This distinction also prevents a dangerous causal overread. A graph can store
`warehouse_failure caused release_delay`; traversal can retrieve that edge. The
edge remains an assertion whose extraction, source, time, and verification need
their own contracts. Connectivity does not turn co-occurrence into causality.


## 1c Historical claim audit

### Standard RAG and graph retrieval

| Article claim | Finding |
| --- | --- |
| Similarity retrieval cannot answer connected questions | `[D]` Directionally sound for naive chunk-only retrieval, but stated too absolutely. Hybrid RAG can combine vectors, metadata, reranking, query decomposition, and graph/path retrieval. Even the article's own recommended retrieval layer retains vector search. |
| Microsoft GraphRAG proves the causal, multi-hop architecture described | `[X]` The primary GraphRAG paper evaluates global query-focused summarization; questions such as “what are the main themes?”; over million-token corpora. It reports gains in answer comprehensiveness and diversity over conventional RAG for that question class. It does not establish that extracted causal paths are true or prove the article's sales/supplier/warehouse chain use case. |
| Graphs directly return connected facts | `[D]` A graph query can return paths when the required nodes, edge types, temporal qualifiers, and identities were modeled correctly. Entity resolution and schema quality are preconditions, not cleanup details. |
| Gaps in a graph reveal what the system does not know | `[R]` A missing edge may reveal missing modeled knowledge, failed ingestion, extraction error, ontology mismatch, unresolved identity, permissions, or genuinely absent evidence. Absence in the graph is not automatically known absence in the world. |
| “The graph beats the model size. Consistently.” | `[R]` No identified primary source in the article supports this universal formulation. Graph structure can improve specific retrieval tasks, but model quality, extraction quality, ontology, corpus, query class, and evaluation all remain material. |
| Microsoft, Stanford, and MIT independently proved the architecture | `[X]` The references do not substantiate that provenance. Microsoft GraphRAG is relevant evidence; Stanford's DSPy is an LM-programming and optimization framework, not an independent GraphRAG proof; the article supplies no identified MIT graph-engineering study. |
| A paper compares 26 open-source models on knowledge-graph engineering and reaches the quoted conclusion | `[R]` The article does not name or link the paper, and a targeted search did not identify a matching primary source. This claim should not guide architecture until the paper and task design are supplied. |

Microsoft's own repository further narrows the maturity claim: `[D]` GraphRAG is
a research project, is largely in maintenance mode, does not accept feature PRs,
is not an officially supported Microsoft offering, warns that indexing can be
expensive, and recommends dataset-specific prompt tuning. That makes it useful
prior art and a possible library dependency, not a production orchestration
foundation.

### Kimi K3 and long context

| Article claim | Finding |
| --- | --- |
| Kimi K3 supports 1,048,576 tokens | `[D]` Verified as Moonshot's declared context length in the Kimi K3 model materials and technical report. This is a capability limit, not evidence that every token is recalled or reasoned over uniformly. |
| Kimi K3 uses Kimi Delta Attention and Attention Residuals | `[D]` Verified by the Kimi K3 report. KDA improves sequence-length efficiency; AttnRes improves information flow across model depth. |
| KDA gives “up to 6.3× faster decoding in million-token contexts” for Kimi K3 | `[X/D]` The 6.3× figure comes from the earlier Kimi Linear 48B-A3B matched comparison against full-attention MLA: 1.84 ms versus 11.48 ms time per output token at 1M context, with memory allowing larger batches. The same paper also reports roughly 2.3× single-stream decoding speed and calls 6.3× a theoretical/throughput benefit. Kimi K3 adopts KDA, but the article transfers the exact Kimi Linear benchmark to K3 and to production economics without equivalent evidence. |
| A 1M window means the entire relevant subgraph fits, so truncation disappears | `[X]` Graph size is unbounded, provider limits are maxima rather than retrieval policy, and irrelevant or weakly ranked graph material can still degrade quality and cost. A graph exists to select a bounded evidence subgraph; sending everything defeats that design even when it fits. |
| AttnRes means reliable connection of position 5,000 to position 800,000 | `[R]` AttnRes is a depth-routing architecture, not a guarantee of exact long-range factual recall. Long-context benchmark results support capability, not that specific reliability claim. |
| Kimi K3 is the best model for this architecture | `[R]` This is a product judgment without a graph-specific comparative evaluation. K3's long-context capacity makes it a credible candidate. It does not remove the need to compare answer quality, extraction precision, latency, token cost, and provider behavior on the target corpus. |

For Petrus, context capacity is an operational model
property, not durable memory and not process state. Kimi K3 should be one
replaceable model binding. Provider request, model/version, bounded input,
structured result, and failure become Activity facts; the Net decides what
happens next.

### Cost and quality figures

The article appropriately warns that “85% lower cost, 18% better accuracy” is
not universal, but its surrounding prose still invites generalization.

`[D]` Those figures are traceable to the 2026 ChatP&ID preprint for engineering
Piping and Instrumentation Diagrams. It reports 18% better accuracy than raw
image inputs and 85% lower token cost than directly ingesting smart P&ID files.
That is one domain, corpus representation, baseline, and evaluation. It does not
estimate gains against a production vector RAG system or Petrus.

The broader claim “costs less per useful answer” therefore remains `[R]` until a
target application measures extraction/indexing amortization, update cost,
retrieval tokens, answer calls, verification calls, storage, latency, and
operator correction together.

### The synergized update loop

The article recommends letting the model extract and write new facts while the
graph supplies context for later answers, claiming the system gets measurably
smarter every time it answers.

That update needs an acceptance policy.

- `[D]` Iterative graph enrichment is a real architecture pattern.
- `[X]` An answer does not necessarily add knowledge; it may duplicate,
  misresolve, overgeneralize, or contradict existing claims.
- `[D]` Entity resolution, evidence references, temporal validity, ontology
  checks, contradiction policy, and human/domain verification determine whether
  an update improves the graph.
- `[D]` Silent overwrite is the wrong update model. Candidate claim,
  verification disposition, accepted assertion, supersession, and retraction
  should remain distinguishable.

Petrus's “capture before meaning” principle is the stronger formulation: retain
identified raw source evidence and infrastructure-owned progress before a model
interprets it. An LLM extraction is a claim about a source, not the source
itself. Its acceptance into a knowledge projection should be explicit,
replayable, and attributable.

“Build it in one week” is reasonable for a narrow prototype with one corpus and
five questions. It is not a credible estimate for trustworthy ingestion,
identity resolution, temporal/versioned truth, contradiction handling,
authorization, recovery, and production evaluation.


## 1d Composition recommendation

A future application can capture identified source evidence, extract candidate
assertions, resolve identity/schema, verify, and publish through an idempotent
Activity. A query route can retrieve bounded evidence, generate an answer, and
verify support or report insufficient evidence. This is a design inference,
not a delivered workflow.

The graph store may own accepted application knowledge. Stable source/assertion
IDs, temporal validity, model/program and schema versions, contradiction policy,
acceptance, supersession, and retraction must remain explicit. Reconcile an
ambiguous graph commit by lookup before retry. External graph queries belong in
Activities; guards and filters classify already available facts.

GraphRAG/Neo4j can supply indexing and retrieval; DSPy can supply a versioned
model program; Kimi or another model can supply inference. Model context,
provider sessions, saved programs, and Kimi Code's session files are not
workflow checkpoints. A reachable MCP server grants neither application
authority nor durability. Keep context selection and budgets consumer-owned,
and keep the local first-motion path free of mandatory external infrastructure.

A concrete Kimi Code integration would need a separately qualified coarse
Activity or Agenticus public-proposal boundary, following the
[Net-owned-loop decision](../../decisions/records/2026-08-05T0923Z-net-owned-pi-loop-mirrors-a-bounded-public-seam.md).
A retrieved assertion cannot authorize external mutation, and a generated answer
cannot update accepted knowledge without verification. The
[capture-before-meaning principle](../../../product/principles.md)
already owns the general source/interpretation distinction.

## 1e Revisit condition and experiment seed

If a concrete application needs graph-grounded answers, the smallest useful
experiment is not “install Neo4j and connect an agent.” It is one bounded corpus,
one versioned ontology, and a fixed evaluation set comparing:

1. vector-only retrieval;
2. entity + one-hop retrieval;
3. bounded path/community/temporal retrieval; and
4. at least two model/cost tiers.

Measure answer correctness, relationship extraction precision/recall, entity
resolution errors, evidence citation coverage, contradiction and supersession
behavior, insufficient-evidence calibration, indexing/update cost, query tokens,
latency, duplicate-delivery idempotence, and recovery across a forced crash
between graph commit and Activity-result acceptance.

That experiment would test both sides of the claimed value: whether graph
structure improves the application's answers and whether Petrus makes the
pipeline durably understandable. Until a consumer requests it, this remains an
experiment seed rather than a Delivery candidate.


## 1f Closure

Resume only when an application needs graph-grounded answers and supplies a
bounded corpus and evaluation questions. The research does not change the
current [CV20 direction](../../roadmap/cv20-approachable-petrus/index.md).
ES-056 later promoted separately; this earlier comparison supplied no promotion
evidence. Broad graph/model superiority and the untraceable 26-model claim
remain excluded from project direction.
