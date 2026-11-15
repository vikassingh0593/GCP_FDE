# Demo outputs

Generated 2026-10-20 14:23 UTC.

| case | demo | file | tools | result | seconds |
|---|---|---|---|---|---|
| D1 | Current | [01_current.md](01_current.md) | search_current | PASS | 40.2 |
| D2 | Historical | [02_historical.md](02_historical.md) | search_historical | FAIL (reasoning) | 26.5 |
| D3 | Identifier | [03_identifier.md](03_identifier.md) | lookup_document | PASS | 22.2 |
| D4 | Table | [04_table.md](04_table.md) | compare_studies | PASS | 45.7 |
| D5 | Unsupported | [05_unsupported.md](05_unsupported.md) | search_current | PASS | 5.1 |
| D6a | Agentic: current | [06_agentic.md](06_agentic.md) | search_current | PASS | 22.6 |
| D6b | Agentic: historical | [06_agentic.md](06_agentic.md) | search_historical | PASS | 42.6 |
| D6c | Agentic: high-risk (patient) | [06_agentic.md](06_agentic.md) | escalate | PASS | 17.4 |
