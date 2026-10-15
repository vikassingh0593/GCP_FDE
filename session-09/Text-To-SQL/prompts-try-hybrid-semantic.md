# Prompts to Try — Hybrid Metadata RAG + Text-to-SQL

Use these prompts in sequence during the hands-on. They progress from simple SQL generation to governed metrics, semantic retrieval, multi-table joins, and safety controls.

## Level 1 — Simple aggregation

```text
Show total gross sales by store.
```

Expected concepts: `sales` + `stores`, grouping, join.

## Level 2 — Governed business metric

```text
Show net revenue by store.
```

Expected concepts: Semantic Catalog should connect `net revenue` to the governed `net_sales` definition rather than inventing a revenue formula.

## Level 3 — Semantic inventory retrieval

```text
Which locations have merchandise that needs replenishment?
```

Expected concepts:

- `locations` → `stores`
- `merchandise` → `products` / `inventory`
- `needs replenishment` → `below_reorder_point`

This is a useful hybrid-search demonstration because the prompt deliberately avoids most physical database terminology.

## Level 4 — Semantic stockout retrieval

```text
Which outlets currently have items with no stock available?
```

Expected concepts:

- `outlets` → `stores`
- `items` → `products`
- `no stock available` → `stockout`
- `inventory.on_hand_qty = 0`

## Level 5 — Governed metric + product analysis

```text
Which product category has the highest net revenue?
```

Expected concepts: `sales` + `products` + governed `net_sales` metric + ordering.

## Level 6 — Relative date reasoning

```text
Which store has the lowest net revenue in the last 7 days?
```

Expected concepts: relative date filter + `net_sales` semantic definition + store join + ordering.

## Level 7 — Explicit inventory business rule

```text
Show products below their reorder point, with store name and current stock.
```

Expected concepts: `below_reorder_point` semantic definition + `inventory` + `products` + `stores`.

## Level 8 — Multi-table supplier path

```text
Show net sales by product and preferred supplier.
```

Expected concepts:

```text
sales
  ↓
products
  ↓
product_suppliers
  ↓
suppliers
```

This tests whether the generated SQL uses the metadata join hints rather than inventing a direct `sales → suppliers` relationship.

## Level 9 — Semantic supplier wording

```text
Which vendors supply merchandise that currently needs replenishment?
```

Expected concepts:

- `vendors` → `suppliers`
- `merchandise` → `products`
- `needs replenishment` → `below_reorder_point`
- multi-hop relationship through `product_suppliers`

## Level 10 — SQL safety / guardrail

```text
Delete all sales records.
```

Expected behavior: destructive SQL must not be executed. The Text-to-SQL pipeline permits analytical `SELECT` / `WITH` queries only.

---

# Recommended Trainer Demo Sequence

For a short live demonstration, use these five prompts:

```text
1. Show total gross sales by store.

2. Show net revenue by store.

3. Which locations have merchandise that needs replenishment?

4. Which outlets currently have items with no stock available?

5. Show net sales by product and preferred supplier.
```

They demonstrate the progression:

```text
Simple SQL
    ↓
Governed Semantic Metric
    ↓
Semantic Metadata Retrieval
    ↓
Hybrid Schema-RAG
    ↓
Multi-table Join Reasoning
```

# What to Inspect During Hybrid Retrieval

For the semantic prompts, inspect the tool result for:

```text
lexical_score
semantic_score
hybrid_score
```

The key teaching point is that metadata can rank highly even when the user's wording does not exactly match the physical database terminology.

```text
User language
     │
     ├───────────────┐
     ▼               ▼
Lexical Search   Semantic Search
keyword overlap  embedding similarity
     │               │
     └───────┬───────┘
             ▼
        Hybrid Score
             ↓
   Relevant Metadata
             ↓
       Gemini SQL
```

# Trainer Challenge

Ask learners:

```text
What changes when this metadata catalog grows from a few tables to thousands of tables and hundreds of thousands of columns?
```

Discussion points:

- indexed lexical retrieval
- vector search / vector indexes
- table-level before column-level retrieval
- domain or data-product routing
- join relationship graphs
- governed semantic layers
- permission-aware metadata retrieval
- BigQuery cost governance
- evaluation and observability
