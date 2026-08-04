# Roadmap

Where viyapy is heading. The library today is a hardened, typed client for
**inspecting decision flows** and **executing MAS modules**; the goal from here is
to grow it into a complete Intelligent Decisioning client while keeping the same
quality bar — full typing, tested error paths, and support for both Viya 3.5 and
Viya 4.

!!! note "Directional, not a commitment"
    This roadmap describes **intended direction and priority order**, not
    promises or timelines. Priorities can shift as we learn and as SAS's APIs
    evolve. There are deliberately **no dates**. New capabilities ship as
    additive, non-breaking **minor releases**.

## Guiding principles

- **Additive and non-breaking.** New capability is layered on; existing APIs
  don't change out from under you.
- **Typed and tested.** Every new resource gets a typed model and tested
  behavior, including its error paths.
- **Both generations stay first-class.** Viya 3.5 and Viya 4 differences are
  absorbed by the dialect layer.
- **Reads before writes.** Within each area, discovery and inspection land before
  create/update/delete, so value arrives early and the write surface is small and
  well understood when it lands.

## What we have today

- Read a decision flow and its model steps (`client.decisions`).
- Execute a MAS module step synchronously (`client.mas.execute`).
- A hardened HTTP stack: pluggable auth, typed errors with actionable context,
  retries with backoff, and bearer-token redaction.

## Where we're going, in priority order

1. **Know a module before you call it.** List and fetch MAS modules, read a
   step's typed signature, and validate inputs (client-side, and against the
   server) so bad calls fail fast with a clear message.
2. **The full execution surface.** Synchronous, fire-and-forget, and
   timed-execution modes; binary (base64) inputs and outputs; execution
   correlation metadata; and creating, updating, and removing modules.
3. **Discover and inspect decisions.** List decision flows, browse their revision
   history, and retrieve their generated code.
4. **Author decisions.** Create, update, and delete decision flows — including a
   typed builder so you can compose flows in Python instead of hand-writing SAS
   JSON.
5. **Author business rules.** Manage the rulesets and rules that decisions
   reference.
6. **Publish to runtime.** List publishing destinations and publish decisions,
   rulesets, and modules to them.
7. **Batch scoring at scale.** Score CAS tables through a published decision for
   high-volume workloads — the throughput path beyond single-request execution.

## Have an opinion?

Priorities are shaped by real use. If something here matters more (or less) for
your work, or you're missing a capability entirely, please
[open an issue](https://github.com/Shai-Alit/viyapy/issues) — it genuinely
influences ordering.
