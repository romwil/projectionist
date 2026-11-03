# Comprehensive Architectural, Security, and Code Review Protocol

Execute a deep-tissue architectural, performance, and security review across the current codebase and active changeset.

Abandon conversational filler and superficial stylistic feedback. Focus on architectural soundness, operational bottlenecks, concurrency risks, and security boundaries.

Execute the audit across four sequential passes:

## PASS 1: Architectural Integrity, Modularity & Dead Weight
1. Structural Seams & Coupling: Identify leaky abstractions, circular dependency risks, and unnecessary coupling between domain logic and transport adapters.
2. Codebase Cruft & Redundancy: Pinpoint duplicate implementations of the same concept, dead code paths, and deprecated compatibility shims ready for deletion.
3. Domain Purity: Flag instances where presentation models bleed into storage tiers, or storage engine specifics bleed into the public interface.

## PASS 2: Resource Footprint, Concurrency & Scale Resilience
1. Contention & Deadlocks: Inspect asynchronous file IO, database connections, and memory-locking coordinators. Identify race conditions, missing lock release guarantees, and potential unhandled task future deadlocks under load.
2. Storage & Memory Leakage: Identify unbounded data structures, long-lived unmanaged caches, missing object disposal, and potential SQLite WAL growth traps (long-lived read transactions blocking checkpointing).
3. Client-Side Constraints: Audit browser and client delivery code for memory leaks (DOM element proliferation), unthrottled render loops, layout thrashing, and excessive CPU/GPU consumption on embedded or low-spec devices.

## PASS 3: Security Perimeter, Isolation & Threat Boundaries
1. Ingress & Access Gate Bypasses: Audit every route and interface against unauthenticated access, improper peer classification, spoofed network headers, and URL traversal tricks.
2. Injection & Memory Overflows: Inspect all inputs for unsafe deserialization, prompt injection vectors, unescaped raw HTML/DOM injections, and missing payload byte caps.
3. Secret & Credential Hygiene: Verify zero static leaks, ensure constant-time comparison on tokens/hashes to defeat timing oracles, and confirm sensitive data isolation across system boundaries.

## PASS 4: Privacy Posture & Boundary Data Leakage
1. Information Minimization: Audit open and unauthenticated endpoints for data egress leakage (internal IDs, timestamps, usernames, client tokens, network topology).
2. Identity Leakage: Ensure anonymous surfaces never join or correlate with user account records in open responses.
3. Asset Proxy & Token Scrubbing: Confirm third-party tokens and upstream URLs are fully abstracted behind authenticated or private-peer proxies, never shipped naked over the wire.

## Required Output Structure

### 1. The Architectural Verdict
- Cruft (Immediate excision candidates)
- Structural Seams (Refactor required before further feature growth)
- Hardened Wins (Patterns to standardize across the repo)

### 2. Detailed Findings Register
Present each finding formatted as:
- Finding ID: [PASS-SEVERITY-NUMBER] (e.g., P2-CRIT-01)
- Category: [Architecture | Performance | Security | Privacy]
- Severity: [Critical | High | Medium]
- Location: `path/to/file.ext:line_number`
- The Reality: Concrete analysis of why the implementation fails or degrades under pressure.
- Mitigation Code: Complete, production-ready replacement block.

### 3. Operational Sprint Plan (Parallel Agent Threads)
Organize remediation into a decoupled sprint matrix for parallel Cursor Agent panes:
- Thread A: Core Perimeter & Security Hardening (Auth, Ingress, Input Sanitization)
- Thread B: Storage, Concurrency & Engine Lifecycle (DB transactions, Lock management, WAL hygiene)
- Thread C: Edge Delivery & Low-Power Client Optimization (Kiosk runtime, Caching, SSE/event bridges)
- Thread D: Cruft Cleanout & Domain Decoupling (Dead paths, duplicate layouts, schema migrations)