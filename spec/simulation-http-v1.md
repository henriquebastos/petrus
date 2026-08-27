# Simulation HTTP profile 1

This profile exposes one application-owned, fixed, already-admitted Petrus Net.
It is a synchronous trusted-network transport with no authentication. CORS
restricts browser access to one configured exact HTTP(S) origin but is not an
authorization boundary.

## Profile

`GET /v1/simulation-profile` returns the exact strict-JSON fixture
`observation/simulation-service-profile-v1.json`: format
`petrus-simulation-service-profile`, integer version 1, profile
`implementation-free-v1`, the canonical definition, and every runner and
transport bound. The definition is captured before socket binding.

The exact definition is a race precondition. It is not provenance, a source or
revision identity, a signature, or an implementation identity. Object member
order is insignificant; JSON types and array order are exact.

## Simulation

`POST /v1/simulations` accepts exactly `expected_definition`,
`initial_marking`, and `max_actions`. The marking uses the protocol-v1 sorted
place/token shape and each token has exactly `color` and strict-JSON `data`.
The response is one [Petrus Net document](net-document-v1.md). It carries the
profile's exact definition and one `simulated` lineage entry per canonical
History record. Every entry carries its complete marking directly and keeps
the corresponding History record in non-authoritative metadata. The first
entry's metadata also carries profile, scenario, and outcome context. There is
no separate simulation-result portable format.

Requests require exactly one valid `Content-Length`, an uncompressed
`application/json` body (optionally `charset=utf-8`), and no query. The body is
at most 1,048,576 bytes. Exactly one `Origin` and `Content-Type` are required;
`Expect`, transfer encoding, and content encoding are refused. This combined transport bound can exclude a request
whose definition and marking independently reach their profile maxima.

The server speaks HTTP/1.0 and serves exactly one parsed request per connection.
Its five-second connection timeout bounds incomplete bodies and response writes.
The application exclusively cedes the immutable `BuiltNet` to the server for
the server's lifetime. Returned profile values are detached copies.

Only one simulation runs at a time; overlap is refused without a queue. A
disconnect is not cancellation and causes no retry: admitted bounded work
finishes and its result is discarded. There is no persistence, job, status,
run ID, continuation, or retry protocol.

## Routes and errors

The profile route allows `GET, OPTIONS`; the simulation route allows
`POST, OPTIONS`. Every request requires the configured exact `Origin`.
Responses set that exact `Access-Control-Allow-Origin`, `Vary: Origin`, no
credentials, and route-specific preflight method/header declarations.

The decoder owns wire structure, exact types, and ordering. A foreign place,
typed-place color mismatch, or runner resource refusal is a structurally valid
scenario delegated to the simulation profile and returns 422. Definition
mismatch is checked before simulation and returns 409. Unexpected producer
failures return 500 without details.

Errors are compact sorted strict JSON shaped exactly as
`{"error":{"code":"...","message":"..."}}`. Codes are `invalid_request`,
`origin_not_allowed`, `not_found`, `method_not_allowed`,
`definition_mismatch`, `length_required`, `payload_too_large`,
`unsupported_media_type`, `simulation_rejected`, `simulation_busy`,
`server_shutting_down`, and `internal_error`. Internal exception details never
cross the wire.

| Condition | Status |
| --- | --- |
| Parsed request with invalid strict JSON, wire shape, types, ordering, target, or `Expect` | 400 |
| Missing, duplicate, comma-joined, signed, spaced, or otherwise invalid `Content-Length` | 411 |
| Lexically oversized body length | 413 |
| Missing/duplicate/wrong content type or any transfer/content encoding | 415 |
| Structurally valid scenario rejected by `implementation-free-v1` | 422 |
| Definition mismatch | 409 |
| Simulation overlap | 429 |
| Unexpected producer failure | 500 |

These exact JSON errors apply only after the Python standard library has
successfully parsed the request line and headers. Malformed pre-handler HTTP
syntax remains the standard library server's territory.
