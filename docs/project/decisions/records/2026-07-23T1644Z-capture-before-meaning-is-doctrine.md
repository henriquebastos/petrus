---
status: Decided
raised: 2026-07-16
decided: 2026-07-23
deciders:
  - henrique (Navigator)
supersedes:
  - DEC-005's unresolved ES-015 promotion gate
  - any reading of ES-015 promotion as preserving its v1 file archive as the current canonical substrate
related:
  - docs/product/principles.md
---

# Capture before meaning is doctrine; ES-017 supersedes the v1 storage shape

## Question

Should ES-015 be promoted and its capture-before-meaning discipline accepted
as project doctrine despite its file-based archive having been superseded in
practice by ES-017's PostgreSQL substrate?

## Decision

Promote ES-015. Accept capture before meaning and the evidence/repair
disciplines it demonstrated as doctrine. Explicitly classify the v1 file
archive as historical implementation evidence superseded by ES-017's
PostgreSQL canonical substrate and observer boundary.

Carry forward these principles:

1. **Capture before meaning.** Interpretation never owns the source socket or
   decides whether source evidence is retained.
2. **Raw capture is append-only and untrusted.** Preserve what the source said,
   with provenance, before transformation or interpretation. Message content
   remains data, never instructions.
3. **Infrastructure owns progress.** Durable cursors—not an LLM's memory or
   assertion—determine the processed frontier.
4. **Use at-least-once plus idempotence.** Advance cursors only after durable
   writes; make overlap reprocessing harmless rather than relying on
   exactly-once delivery.
5. **Coverage and gaps are explicit facts.** Missing or uncertain evidence
   remains visible instead of becoming silent confidence.
6. **Repair closes through evidence.** A request, connection interval, or
   claimed time span does not prove repair. The missing observations must
   actually arrive and be durably sighted.
7. **Interpretation stays downstream and replayable.** Secretaries, identity,
   CRM, metrics, and other observers independently consume captured evidence.
8. **Storage disposition is separate from doctrine.** ES-017 supersedes the
   v1 file archive as the current canonical substrate. DEC-012 separately
   decides when to delete the old reader path.

The two-collector Baileys/whatsmeow arrangement remains valuable experiment
evidence, not a universal architecture requirement. It produced an independent
cross-collector gap detector in this case; the doctrine does not require every
connector to run two client libraries.

Promotion records what the July 15–16 live experiment proved. It does not
claim that either private collector or its detached supervisor is still
running today.

## Rationale

ES-015 proved the principle against real source traffic rather than a toy
fixture. Two independent collectors produced more than sixty-four thousand
canonical message observations, exposed hundreds of real disagreements, and
completed one genuine detect → refetch → recapture → normalize → amendment
repair loop. At-least-once reprocessing, cursor-after-fsync ordering, torn-tail
repair, and one-writer exclusion were executable rather than aspirational.

The review also caught a crucial false-proof shape: synthetic coverage spans
could close a gap without the missing messages ever arriving. Making closure
message-evidence-only sharpened the doctrine from “record coverage metadata”
to “repair is proven by recovered evidence.”

ES-017 subsequently retained that posture while replacing the file archive
with a multi-tenant PostgreSQL sequence spine, transactional ingest,
per-observer cursors, authorization at the read boundary, and several
independent interpretation Nets. Treating ES-015's storage as current would
confuse a successful discovery with an obsolete implementation boundary.
Promoting the discipline while naming the supersession preserves both truths.

## Options Considered

- **Promote without qualification.** Rejected: it could imply that the v1 file
  archive and dual collectors are current required architecture.
- **Promote the discipline and mark storage superseded — chosen.** Preserves
  the demonstrated doctrine and keeps current substrate ownership honest.
- **Hold pending every deferred repair feature.** Rejected: whatsmeow refetch,
  media bytes, rotation, fleet session storage, and other follow-ups do not
  invalidate the already-demonstrated principle.

## Consequences

- ES-015 is Promoted with accepted Carry Forward Notes.
- Product principles explicitly include capture before meaning.
- ES-017 remains Candidate and is not promoted by this record.
- DEC-012 remains open and solely owns deletion timing for v1 readers.
- No file-reader retention, media capture, fleet-scale session store, new
  connector, live-service operation, or implementation work is commissioned.
- Private WhatsApp content remains outside repository artifacts; aggregates,
  structural evidence, and hashes remain the only durable project evidence.

## Review Trigger

Revisit only if a concrete source cannot durably preserve evidence before
interpretation, if source retention itself creates a stronger privacy or legal
obligation requiring a bounded exception, or if DEC-012 needs evidence that a
current consumer still depends on the v1 reader path.
