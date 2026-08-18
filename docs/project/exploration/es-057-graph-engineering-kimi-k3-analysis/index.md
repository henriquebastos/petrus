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

# Graph engineering and Kimi K3 against Petrus

## Inquiry

What does the article “Graph Engineering with Kimi K3” and its referenced stack
actually establish, which graph does each part own, and should any of it change
Petrus's proposal for a progressively approachable durable agentic Petri-net
runtime?

The article was published on 2026-08-12. Sources were checked on 2026-08-18.
Claims below use Petrus's evidence grades: `[E]` executable repository evidence,
`[D]` authoritative source documentation, `[R]` reported but unverified, and
`[X]` refuted or materially contradicted by the checked source.

## Executive conclusion

The article is directionally useful and architecturally imprecise.

Its durable lesson is **structure around a model matters more than treating the
model as the system**. That strongly agrees with Petrus. Its proposed structure,
however, is a knowledge/retrieval graph for grounding answers. Petrus's structure
is an executable Petri net whose marking and append-only History make work
replayable, recoverable, and inspectable. One does not replace the other.

The article's eight-stage pipeline is a good **application process to run on
Petrus**, not a competing runtime and not a reason to add knowledge-graph
semantics to Impetus. Neo4j can own an application knowledge projection; Kimi K3
or another model can perform bounded extraction and answer Activities; GraphRAG
or Neo4j GraphRAG can provide indexing/retrieval components; DSPy can optimize a
versioned model program; and Kimi Code can be an optional agent runtime or
connector. Petrus should continue to own process identity, durable progression,
retries, timers, authority, effect acceptance, recovery, and replay.

The article does not justify changing ES-056. The current proposal remains the
right one: one readable flow to first motion, lowering to the same canonical Net
and runtime semantics. A graph-engineering example could later pressure-test that
experience, but only after the zero-agent first-motion route is coherent. It is
not evidence to promote ES-056 or broaden Agenticus support now.

## The four graphs must remain distinct

“Graph” is doing too much work in the article. Four different structures are in
scope:

| Structure | Nodes and edges mean | Correct owner | Not evidence of |
| --- | --- | --- | --- |
| Knowledge graph | Domain entities and asserted relationships, with sources and time | Application data store such as Neo4j | Execution order, retry, or recovery |
| Retrieval/index graph | Chunks, entities, communities, embeddings, and paths used to select context | GraphRAG/retrieval subsystem | Truth of the extracted relationships |
| Agent/tool loop | Model decisions and tool calls | Kimi Code or an Agenticus program, bounded by host authority | Durable business-process state by itself |
| Petrus execution net | Places, typed tokens, transitions, guards, timers, and Activity boundaries | Impetus Net + one Instance History | A general-purpose domain knowledge database |

`[D]` Microsoft GraphRAG describes itself as a pipeline and transformation suite
that extracts structured data from unstructured text. `[E]` Petrus defines the
durable thing as the Net Instance—marking plus one canonical History—and places
agents inside that Net as handler behavior. The shared word “graph” does not make
the models interchangeable.

This distinction also prevents a dangerous causal overread. A graph can store
`warehouse_failure caused release_delay`; traversal can retrieve that edge. The
edge remains an assertion whose extraction, source, time, and verification need
their own contracts. Connectivity does not turn co-occurrence into causality.

## Article claim audit

### Standard RAG and graph retrieval

| Article claim | Finding |
| --- | --- |
| Similarity retrieval cannot answer connected questions | `[D]` Directionally sound for naive chunk-only retrieval, but stated too absolutely. Hybrid RAG can combine vectors, metadata, reranking, query decomposition, and graph/path retrieval. Even the article's own recommended retrieval layer retains vector search. |
| Microsoft GraphRAG proves the causal, multi-hop architecture described | `[X]` The primary GraphRAG paper evaluates **global query-focused summarization**—questions such as “what are the main themes?”—over million-token corpora. It reports gains in answer comprehensiveness and diversity over conventional RAG for that question class. It does not establish that extracted causal paths are true or prove the article's sales/supplier/warehouse chain use case. |
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
| KDA gives “up to 6.3× faster decoding in million-token contexts” for Kimi K3 | `[X/D]` The 6.3× figure comes from the earlier **Kimi Linear 48B-A3B** matched comparison against full-attention MLA: 1.84 ms versus 11.48 ms time per output token at 1M context, with memory allowing larger batches. The same paper also reports roughly 2.3× single-stream decoding speed and calls 6.3× a theoretical/throughput benefit. Kimi K3 adopts KDA, but the article transfers the exact Kimi Linear benchmark to K3 and to production economics without equivalent evidence. |
| A 1M window means the entire relevant subgraph fits, so truncation disappears | `[X]` Graph size is unbounded, provider limits are maxima rather than retrieval policy, and irrelevant or weakly ranked graph material can still degrade quality and cost. A graph exists to select a bounded evidence subgraph; sending everything defeats that design even when it fits. |
| AttnRes means reliable connection of position 5,000 to position 800,000 | `[R]` AttnRes is a depth-routing architecture, not a guarantee of exact long-range factual recall. Long-context benchmark results support capability, not that specific reliability claim. |
| Kimi K3 is the best model for this architecture | `[R]` This is a product judgment without a graph-specific comparative evaluation. K3's long-context capacity makes it a credible candidate. It does not remove the need to compare answer quality, extraction precision, latency, token cost, and provider behavior on the target corpus. |

The Petrus consequence is simple: context capacity is an operational model
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

That is the highest-risk part of the proposal.

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

## Tool-by-tool fit with Petrus

| Tool | What it actually owns | Petrus composition boundary | What must not become authoritative |
| --- | --- | --- | --- |
| **Kimi K3** | Model inference with large context, reasoning, vision, and tool-call generation | A versioned model Activity or a qualified Agenticus runtime binding | Prompt context, provider session, or model reasoning as process truth |
| **Kimi Code** | Interactive coding-agent loop, TUI, tools, MCP, plugins, subagents, hooks, and resumable local sessions | Optional Agenticus adapter/profile or one coarse bounded Activity; finer integration routes individual effects through scoped Hands/Activities | Its conversation loop or `wire.jsonl` as canonical application History |
| **Microsoft GraphRAG** | Offline extraction/indexing pipeline, entity graph, communities/reports, embeddings, and query context | A library behind indexing/query Activities, or stages represented as explicit transitions | Its sequential Python pipeline state as durable workflow state |
| **Neo4j** | Transactional application graph storage, Cypher, indexes, vector and graph retrieval | External application store accessed by idempotent Activities/connectors | A second Petrus execution history or hidden scheduling authority |
| **Neo4j GraphRAG Python** | Retrievers, generation facade, and experimental knowledge-graph construction components | Activity implementation for extraction, resolution, retrieval, or answer generation | Experimental pipeline success as proof of accepted process completion |
| **DSPy** | Composable LM programs plus prompt/weight optimization and saved program artifacts | Versioned extraction/query/answer Activity implementation; optimization as a separate batch process | Saved program state as an in-flight workflow checkpoint |
| **MCP** | Tool/resource protocol exposed to an agent client | Connector or scoped Hands transport after installation authority is resolved | Orchestration, authorization policy, idempotency, or durable state merely because a server is reachable |

### Kimi Code is adjacent to Agenticus, not an execution substrate replacement

`[D]` Kimi Code reads and edits files, executes shell commands, fetches web
pages, uses MCP, runs subagents, and supports lifecycle hooks. Its current
session design also has meaningful local persistence and replay. That is stronger
than an ephemeral chat loop.

It is still agent-centric session machinery rather than a general durable
business-process runtime. A coarse Petrus integration could execute one bounded
Kimi task as an Activity and retain the session/artifact references. A finer
integration could mirror Petrus's Pi precedent: stop at a public model/tool
proposal seam, let a Net own repetition and ordered dispatch, and route effects
through capability-scoped Hands. Which boundary is justified depends on a
concrete consumer; no Kimi Code profile is commissioned by this comparison.

### Neo4j is useful application state, not canonical process state

Neo4j can be authoritative for the application's accepted current knowledge
graph while Petrus History remains authoritative for how one process Instance
progressed. Those claims do not conflict if the seam is explicit:

- stable source and assertion identities make graph writes idempotent;
- a completed write Activity freezes the accepted database outcome before the
  Net advances;
- extraction candidates, verification, rejection, supersession, and publication
  remain separate process facts;
- rollback or ambiguous commit is reconciled through lookup rather than guessed;
- graph schema/version and model-program version accompany derived assertions;
- graph queries are Activities because guards and filters may not imperatively
  read external state.

Not every Neo4j node or property belongs in Petrus History. The knowledge graph
is application territory. History needs enough identified facts and result
references to explain and recover the process without copying an external
database into the event log.

### DSPy reinforces the right lesson, but supplies no durability

DSPy's useful idea is to program modular LM behavior and optimize it against
examples and metrics rather than maintain a pile of hand-tuned prompts. This
aligns with Petrus's insistence that a model is a component in a system.

DSPy does not provide a knowledge graph, durable timers, restartable Activity
custody, effect idempotency, or canonical event History. A saved DSPy program is
an implementation artifact. Petrus should record which version an Activity used
and own the invocation lifecycle separately.

## Agreement and tension with the Petrus proposal

### Strong agreement

1. **Structure beats model worship.** `[D/E]` Both reject upgrading the model as
   the only answer to system failure. Petrus goes further by making the process
   structure executable and durable.
2. **The model is one component.** `[D/E]` Extraction, resolution, storage,
   retrieval, verification, and update need distinct responsibilities. This
   mirrors Petrus's separation of Net, handlers, Activities, Dispatch, Workers,
   and application stores.
3. **Relationships should be explicit.** `[D/E]` Typed graph edges make domain
   claims inspectable; typed arcs and token flow make process coordination
   inspectable. The semantics differ, but explicitness is shared.
4. **Verification is first-class.** `[D]` The article correctly refuses an
   extraction/answer-only pipeline. Petrus can represent verification,
   contradiction, human judgment, and acceptance as explicit paths rather than
   one prompt suffix.
5. **Corrections should not silently erase the past.** `[D/E]` Timestamping and
   contradiction flags fit Petrus's append-only fact posture, though the
   knowledge store may expose a current projection.
6. **Hybrid retrieval is pragmatic.** `[D]` Vector, entity, path, community, and
   temporal retrieval solve different questions. Petrus need not choose or own
   one retrieval algorithm.

### Material tension

1. **Knowledge claims are called facts too early.** LLM-extracted triples are
   candidate assertions. Petrus should record their source and disposition before
   treating them as accepted knowledge.
2. **The “closed loop” hides execution semantics.** The article assigns planning,
   Cypher generation, gap search, action, and graph update to one agent layer.
   Petrus should expose the recoverable boundaries and let the Net own repetition.
3. **Context is treated as memory.** A million-token prompt is transient
   inference input. Petrus derives context from durable facts for a concrete
   consumer and keeps context selection, order, budget, and provider shaping in
   that consumer until reuse proves a common abstraction.
4. **Agent authority is too broad.** “The graph tells Kimi Code what is true, the
   CLI acts on it” skips installation authority, capability grants, approvals,
   stale-authority fencing, and effect ambiguity. A retrieved claim cannot grant
   permission to mutate the world.
5. **Reliability is missing.** The pipeline says little about identified
   delivery, duplicate ingestion, transactional boundaries, process death,
   bounded retries, timers, cancellation, late results, and reconciliation—the
   concerns Petrus exists to own.
6. **The model choice is prematurely fixed.** Petrus profiles should preserve
   provider differences without making Kimi K3 foundational. A graph pipeline
   should be evaluated with several model/cost tiers.
7. **External infrastructure should not redefine first motion.** Neo4j may be a
   good deployment choice, but ES-056's flagship local route should remain able
   to demonstrate honest first motion without mandatory external infrastructure.

## A Petrus-shaped graph-engineering process

The article's eight layers become clearer when expressed as two coordinated
flows rather than one self-improving agent loop:

```diagram
┌──────────────┐    ┌──────────────┐    ┌──────────────────┐
│ Source       │───▶│ Capture      │───▶│ Extract candidate│
│ archive/API  │    │ identified   │    │ assertions       │
└──────────────┘    └──────────────┘    └────────┬─────────┘
                                                 ▼
                                        ┌──────────────────┐
                                        │ Resolve identity │
                                        │ and schema       │
                                        └────────┬─────────┘
                                                 ▼
                                        ┌──────────────────┐
                                        │ Verify / compare │
                                        │ / human judgment │
                                        └────────┬─────────┘
                                                 ▼
                                        ┌──────────────────┐
                                        │ Idempotent graph │
                                        │ update Activity  │
                                        └──────────────────┘

┌──────────────┐    ┌──────────────┐    ┌──────────────────┐
│ Identified   │───▶│ Hybrid graph │───▶│ Evidence-bounded │
│ question     │    │ retrieval    │    │ answer Activity  │
└──────────────┘    └──────────────┘    └────────┬─────────┘
                                                 ▼
                                        ┌──────────────────┐
                                        │ Verify support / │
                                        │ expose gaps      │
                                        └────────┬─────────┘
                                                 ▼
                                        ┌──────────────────┐
                                        │ Answer or explicit│
                                        │ insufficiency     │
                                        └──────────────────┘
```

Each external model, database, or tool call is an Activity. Pure transitions
classify already recorded results. Candidate assertions never update the graph
merely because generation completed. A later extraction run may supersede an
assertion while preserving evidence and update history. Query-time gaps may
produce identified follow-up work, but they do not recursively grant an agent
permission to ingest arbitrary sources or publish unverified claims.

## Recommendation for Petrus

### Copy

- Make model-independent structure visible before model branding.
- Treat extraction, entity resolution, retrieval, verification, and update as
  distinct user-visible concepts in a future worked example.
- Preserve exact evidence references, relationship types, temporal validity,
  contradiction status, and schema-aware query validation.
- Evaluate hybrid retrieval on real questions rather than assume one technique
  dominates.

### Adapt

- Use a knowledge graph as an **application projection** or optional Arx/read-side
  aid, never as Impetus's canonical process model.
- Let Petrus orchestrate GraphRAG/Neo4j/DSPy/Kimi components through Activities
  with stable identities, retries, and explicit acceptance boundaries.
- If a concrete Kimi Code consumer appears, choose a profile-specific Agenticus
  boundary and qualify it independently; do not infer support from MCP or CLI
  availability.
- Keep context projection consumer-owned and bounded even with a one-million-token
  model.

### Reject

- Do not add generic knowledge-graph nodes or edges to Petrus Net semantics.
- Do not make Neo4j, GraphRAG, DSPy, Kimi K3, Kimi Code, or MCP foundational
  dependencies.
- Do not let an answer write directly into accepted knowledge without an
  identified evidence and verification path.
- Do not equate a prompt window, agent transcript, vector index, or graph database
  with canonical History.
- Do not claim “graph beats model size” or production economics without a
  target-corpus experiment.

## Possible future experiment, not current scope

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

## Disposition

Completed as prior-art analysis.

- No Petrus runtime, specification, or support boundary changes.
- No ES-056 candidate promotion or delivery-map change.
- No new dependency or Agenticus profile.
- The article's architecture is retained as a composable application pattern;
  the untraceable “26 models” claim and broad model/graph superiority claims are
  excluded from project direction.
