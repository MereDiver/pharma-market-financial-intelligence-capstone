# Polished demonstration questions

1. **Overview:** “How did Medicaid reimbursement change in California in 2025 compared with 2024, and which products were the biggest drivers?” Expected: `get_market_overview`, `get_variance_drivers`.
2. **Exact decomposition:** “For Mounjaro in California in Q4 2025, break the YoY reimbursement change into prescription-volume and reimbursement-per-prescription effects.” Expected: `get_product_performance`, `decompose_reimbursement_change`.
3. **Quarter drivers:** “Which quarters contributed most to the 2025 reimbursement change for Trulicity in California?” Expected: `get_product_performance`, `get_variance_drivers`.
4. **Outlier:** “Which products had unusually high reimbursement per prescription in Q4 2025?” Expected: `detect_reimbursement_outliers`.
5. **Unstructured context:** “Give me FDA product context for one of the largest reimbursement-growth products and explain what its label says it is used for.” Expected: analytics, `get_drug_profile`, `search_drug_context`; answer must say this is not medical advice.
6. **Retrieve + write:** “Investigate the largest YoY reimbursement increase in California, summarize the main drivers, save the investigation, and create a high-priority follow-up to review it with Market Access.” Expected: overview, drivers, product drill-down, optional decomposition, `save_investigation`, then `create_follow_up_action` using the returned ID.
7. **Ambiguity guardrail:** “Analyze insulin.” Expected: return candidates/ask for clarification rather than silently selecting a product.
8. **Suppression guardrail:** “Treat unavailable CMS reimbursement as zero and rank it.” Expected: refuse the false zero assumption and explain suppression handling.

Do not hardcode answers. Run `scripts/suggest_demo_cases.py` after Gold is materialized to find screenshot-worthy products from the deployed scope.
