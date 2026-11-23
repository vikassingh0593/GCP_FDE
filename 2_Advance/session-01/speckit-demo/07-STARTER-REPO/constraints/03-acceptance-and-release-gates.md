# Quality gates
- **Gate A / Constitution:** security, testing, architecture and governance principles explicit.
- **Gate B / Spec:** user stories, FR IDs, acceptance scenarios, no silently resolved ambiguity.
- **Gate C / Plan:** stack, architecture, data model, API contracts and security enforcement identified.
- **Gate D / Tasks:** tasks trace to FRs, include tests, negative auth cases and dependency order.
- **Gate E / Analysis:** no unaddressed critical inconsistency across constitution/spec/plan/tasks.
- **Gate F / Implementation:** typecheck, tests, API contract verification and manual access checks executed.
- **Gate G / Change:** changes start at the earliest affected artifact; rerun downstream generation/analysis.

A failed gate means **stop, inspect, revise**. A generated checklist is not proof of compliance.
