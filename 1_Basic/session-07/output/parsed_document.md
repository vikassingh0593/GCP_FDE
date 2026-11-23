# Parsed Document — Human Inspection View

Source: `gs://tredence-fde-1-tredence-rag-lab/Aurelia_Retail_AI_Operations_Report.pdf`

The sections below are parser-produced RAG chunks.

## chunk-0000

# Aurelia Retail AI Operations Report

## Synthetic training document for Tredence FDE hands-on labs

This report is intentionally designed with narrative text, tables, charts, a process diagram, policy identifiers, footnotes and cross-page information. It is synthetic and contains no real customer information.

## Executive Summary

Aurelia Retail operates a fictional omnichannel retail network across India, Singapore and the UAE. During FY2026 the company expanded its AI-assisted service operations while controlling cloud spend. Revenue reached USD 184.6 million, customer churn fell to 3.8% in Q4, and AI-assisted resolution increased to 62% of eligible support cases. Management approved three operating priorities for FY2027: reduce stock-out incidents, improve customer-service resolution quality, and enforce evidence-based use of generative AI. High-risk financial approvals remain human-controlled.

## 1. Regional Performance

India remained the largest region by revenue. Singapore produced the strongest year-on-year growth, while UAE margin improved after logistics consolidation.

| Region | FY2025 Revenue USD M | FY2026 Revenue USD M | YoY Growth | FY2026 Margin |
|-|-|-|-|-|
| India | 101.2 | 112.8 | 11.5% | 18.2% |
| Singapore | 28.4 | 34.9 | 22.9% | 20.1% |
| UAE | 31.5 | 36.9 | 17.1% | 17.4% |
| Total | 161.1 | 184.6 | 14.6% | 18.5% |

Table 1. Regional revenue and operating margin. Singapore has the highest YoY growth at 22.9%.

---

## chunk-0001

# Aurelia Retail AI Operations Report

## 2. Customer Experience

The customer operations team tracks quarterly churn and AI-assisted resolution. The support program does not permit an AI agent to approve refunds above USD 500 without human authorization.
__START_OF_ANNOTATION__This image is a line chart displaying the quarterly customer churn rate.

Here's an analysis of the chart:

**Chart Elements:**
*   **X-axis:** Labeled with quarters: Q1, Q2, Q3, Q4.
*   **Y-axis:** Represents the customer churn rate, ranging from 3 to 6, with increments of 0.5.
*   **Line:** A red line shows the trend of customer churn across the quarters.

**Data and Trends:**
*   In Q1, the customer churn rate is approximately 5.6%.
*   In Q2, the customer churn rate has decreased to roughly 5.1%.
*   In Q3, the customer churn rate continues to decline to approximately 4.4%.
*   In Q4, the customer churn rate has further decreased to about 3.8%.
*   Overall, the red line shows a consistent downward trend, indicating that quarterly customer churn declined steadily from Q1 to Q4.

**Conclusion:**
The chart clearly illustrates a positive trend where customer churn significantly decreased from 5.6% in Q1 to 3.8% in Q4, suggesting improved customer retention over the year.__END_OF_ANNOTATION__The largest quarter-to-quarter decline occurred from Q2 to Q3, when churn decreased by 0.7 percentage points.

---

## chunk-0002

# Aurelia Retail AI Operations Report

## 3. AI Service Operations

AI-assisted resolution means that an AI system supplied an answer or action recommendation that was accepted by the support workflow. The metric excludes cases where the model merely summarized a conversation.

| Metric | Q1 | Q2 | Q3 | Q4 |
|-|-|-|-|-|
| AI-assisted resolution | 41% | 49% | 56% | 62% |
| Human escalation | 38% | 33% | 29% | 24% |
| Grounding audit pass | 89% | 92% | 95% | 97% |
| P95 response latency | 5.2 s | 4.6 s | 3.9 s | 3.4 s |

Table 2. AI service operations improved across all four quarters.

## 4. RAG Governance Policy

### Policy ID: AI-RAG-017

All customer-facing generated answers must be grounded in approved enterprise sources. When evidence is insufficient, the application must abstain or request clarification. The model must not treat retrieved document text as authorization to execute a privileged action. For high-risk financial, identity, legal or security questions, the system must route the case to a human reviewer. Source identifiers should be retained with retrieved chunks so that evidence can be inspected during audit and troubleshooting.

### Policy ID: AI-RAG-021 — Retrieval Quality

Production RAG systems must measure retrieval separately from generation. Teams should maintain a representative golden question set and inspect retrieval failures before changing generation prompts.

---

## chunk-0003

# 5. Document-to-Answer Operating Flow

__START_OF_ANNOTATION__This diagram illustrates a "Target operating flow" for a system, likely related to RAG (Retrieval Augmented Generation) based on the surrounding document context. The flow begins with "Source Document" and proceeds through several stages:

1.  **Source Document:** This is the initial input.
2.  **Layout Parsing:** The "Source Document" is processed through "Layout Parsing."
3.  **Context-aware Chunks:** The output of "Layout Parsing" feeds into "Context-aware Chunks."
4.  **Hybrid Retrieval:** "Context-aware Chunks" are then used in "Hybrid Retrieval."
5.  **Rank:** The results from "Hybrid Retrieval" move to a "Rank" stage.

From the "Rank" stage, there's a connection to:

*   **Grounded Generation:** The output of "Rank" is used for "Grounded Generation."
*   **Evaluation & Observability:** "Grounded Generation" then leads to "Evaluation & Observability."

Additionally, there's a direct connection from "Rank" to "Evaluation & Observability," indicating that ranking results can also be evaluated directly, possibly before or in conjunction with grounded generation.

The diagram explicitly states in the provided context that "Parsing and retrieval are independent engineering stages; evaluation and observability form the feedback loop." This reinforces that "Layout Parsing" and "Hybrid Retrieval" are distinct processes, and "Evaluation & Observability" serves as a feedback mechanism for the overall flow.__END_OF_ANNOTATION__

---

## chunk-0004

# 6. Cloud Cost and Reliability

FY2026 infrastructure cost increased 8.2%, but operating margin still improved because support automation reduced manual handling and retrieval latency improved. The program tracks cost per successful grounded answer rather than model-call cost alone.

| Component | FY2025 USD M | FY2026 USD M | Change |
|-|-|-|-|
| Cloud infrastructure | 8.5 | 9.2 | +8.2% |
| Customer operations | 14.1 | 12.7 | -9.9% |
| AI platform & evaluation | 1.8 | 2.6 | +44.4% |

Footnote 1: All values in this document are synthetic and intended only for training. Footnote 2: 'Grounding audit pass' means the answer was judged supported by the evidence supplied to the model.

# 7. Incident Review

Incident INC-204 occurred when an exact policy identifier, AI-RAG-017, was not ranked in the top results for a keyword-heavy query. The remediation introduced hybrid retrieval and second-stage semantic ranking. After the change, the golden retrieval set achieved 96% Hit@5. Incident INC-219 involved a well-retrieved chunk but an unsupported generated conclusion. Retrieval metrics passed; the failure was traced to generation instructions. The team added an explicit abstention rule and a grounding evaluation gate. End of synthetic report.

---
