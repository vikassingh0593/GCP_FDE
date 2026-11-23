# Course 1 · M2 — Model Engineering & Decisions

## Topic 5 — Model Families, Modalities & Workflow-Based Model Selection

The question is not **"Which model is most popular?"** It is **"Which model is appropriate for this workflow under these constraints, and how do I defend that decision?"**

## Decision Dimensions

### Model Family
Different model families/sizes target different operating points. Select capability that the workflow needs rather than assuming larger is always better.

### Modality
Identify actual inputs/outputs: text, image, audio, video, documents, code or structured data. Modality support is a workflow requirement, not a checkbox.

### Context
Determine what must be available in one inference: current task, retrieved evidence, history, tools, documents. A large context window does not mean you should fill it.

### Reasoning
Classification/extraction may need little reasoning; architecture analysis or planning may need substantially more. Do not pay for reasoning capability the task does not use.

### Latency
Interactive systems may need fast responses; background analysis can often trade latency for deeper processing.

### Quality
Define quality explicitly: classification accuracy, extraction precision, grounded correctness, code correctness, task completion, etc.

### Throughput
Consider requests/sec, batch volume, concurrency, token volume and quotas. A great single-request demo may fail operationally at scale.

### Economics
Think in **cost per successful business task**, including model calls, retries, retrieval, tools, validation and human escalation.

# Defensible Selection Flow

```text
WORKFLOW
  -> MODALITY
  -> QUALITY / REASONING
  -> CONTEXT
  -> LATENCY / THROUGHPUT
  -> PLATFORM / SECURITY
  -> COST
  -> CANDIDATE MODELS
  -> REPRESENTATIVE EVALUATION
  -> DEFEND THE CHOICE
```

## Use Case 1 — High-Volume Support Classification

```text
Modality   : Text
Reasoning  : Low
Context    : Small
Latency    : Important
Throughput : Very high
Quality    : Classification accuracy
```

A fast/cost-efficient candidate may be preferable if it meets the measured acceptance threshold.

## Use Case 2 — Enterprise Architecture Review

```text
Modality   : Text + documents
Reasoning  : High
Context    : Medium/large
Latency    : Less critical
Throughput : Low
Quality    : Trade-off/reasoning quality
```

Stronger reasoning may justify additional latency/cost because decision quality has high value.

## Use Case 3 — Invoice / Screenshot Extraction

```text
Modality   : Text + image/document
Reasoning  : Low/medium
Latency    : Moderate
Throughput : Potentially high
Quality    : Field extraction accuracy
```

Start with modality support, then test extraction quality and economics.

## Use Case 4 — Agent Planner

```text
Modality   : Text + tool state
Reasoning  : Medium/high
Context    : Dynamic
Latency    : Important
Quality    : Task completion + correct tool choices
```

A mixed architecture may be justified: stronger planner, faster worker, deterministic validator.

# One-Minute FDE Defence

```text
I selected __________
because the workflow requires __________
and the important constraints are __________.

We will evaluate it using __________.

I would reject/change this choice if __________.
```

## Hands-On

```bash
python 03_model_selection_demo.py
```

The demo creates a **model-profile hypothesis**, not a universal winning model. The hypothesis must still be evaluated on representative data.
