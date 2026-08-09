# Governed tool manifest

| Tool | Use it for | Data access |
|---|---|---|
| `get_market_overview` | Broad scoped KPIs and top products | Read-only Gold SQL |
| `get_product_performance` | Named-product metrics, comparison, quarterly trend | Read-only Gold SQL |
| `get_variance_drivers` | Positive/negative product, state, quarter, or utilization-type contributions | Read-only Gold SQL |
| `decompose_reimbursement_change` | Exact prescription-volume and reimbursement-per-prescription effects | Read-only Gold SQL |
| `detect_reimbursement_outliers` | Transparent 1.5×IQR flags | Read-only Gold SQL |
| `get_drug_profile` | Structured matched openFDA metadata | Read-only Lakebase |
| `search_drug_context` | Semantic FDA Drug Label chunks | Read-only Lakebase/pgvector |
| `save_investigation` | Explicitly requested investigation persistence | Operational Lakebase write |
| `add_analyst_note` | Explicitly requested note | Operational Lakebase write |
| `create_follow_up_action` | Explicitly requested follow-up | Operational Lakebase write |
| `update_investigation_status` | Explicit workflow status change | Operational Lakebase update |
| `update_follow_up_action` | Explicit action status change | Operational Lakebase update |

There is deliberately no arbitrary SQL tool. Metric, dimension, period, state, product, result limit, UUID, priority, and status inputs are validated; SQL identifiers come only from application allow-lists.

