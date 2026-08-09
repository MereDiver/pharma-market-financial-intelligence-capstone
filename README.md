# Pharma Market & Financial Intelligence Agent

> Agentic investigation of real-world drug utilization, reimbursement and market-performance drivers

## Executive summary

This capstone is a public-data prototype for Pharma Finance/Controlling, Market Access, Commercial Analytics, Portfolio Analytics, and Finance Business Partners. It turns official CMS Medicaid State Drug Utilization records into a governed Spark analytical layer, enriches a deliberately small product set with openFDA metadata and Drug Label text, retrieves label context through Lakebase pgvector, and lets an Agent Bricks agent both investigate evidence and perform safe operational writes.

The application answers questions such as which products or states contributed to reimbursement change, whether movement reflects prescription volume or reimbursement per prescription, which observations are unusual under a transparent statistical rule, and what matched FDA label context says about a product. Users can explicitly save an investigation, add a note, or create/complete a follow-up without granting the agent permission to alter facts.

### Data disclaimer

**Medicaid reimbursement is not manufacturer revenue or net sales.** It is reimbursement paid to pharmacies and reported through the Medicaid program; CMS states that total reimbursement includes Medicaid and non-Medicaid amounts and is not reduced by Medicaid rebates. This repository never labels it manufacturer sales, commercial sales, profit, or realized net price. Reimbursement per prescription is a rate/mix measure and is not equivalent to pharmaceutical list or net price.

This is not a medical diagnosis/treatment assistant, an investment application, or an estimate of confidential pharmaceutical-company performance. openFDA label content is informational product context only.

## Architecture

```text
CMS Medicaid SDUD 2024/2025               openFDA NDC + Drug Label APIs
           |                                          |
           v                                          v
 bounded API pages / streaming CSV           top <= 50 products only
           |                                          |
           v                                          v
 Spark Medallion pipeline                 structured metadata + label text
 Bronze -> Silver -> Gold                           |
           |                                        v
           v                              existing Lakebase project
 Delta / Unity Catalog                    pharma_intelligence schema
           |                              |- drug_documents
           | existing SQL Warehouse       |- drug_embeddings VECTOR(384)
           v                              |- investigations / findings
 governed Finance MCP App <--------------|- analyst_notes / follow_up_actions
           |
           v
 Agent Bricks / Supervisor Agent
           |
           v
 Pharma Intelligence Databricks App
 KPIs | movers | agent | saved investigations | actions
```

Two sources of truth remain deliberately separate: analytical facts live in Delta/Unity Catalog and operational/semantic state lives in the existing Lakebase database. Gold is queried through the existing SQL Warehouse. It is not copied into Lakebase merely to simplify MCP code.

## Capstone requirement mapping

| Universal requirement | Implementation |
|---|---|
| Spark data pipeline | `pipeline/01_ingest_medicaid.py` through `03_build_gold.py`: persisted Bronze/Silver/Gold Delta tables |
| Third-party API | `pipeline/openfda_client.py` calls the no-key-required openFDA NDC and Drug Label APIs; CMS API is also supported |
| Unstructured processing | Real Drug Label sections are normalized, hashed, chunked, embedded with MiniLM, and stored/searched with pgvector |
| Databricks App + frontend | `frontend/` is a professional Flask/HTML/CSS/JS Databricks App with KPIs, movers, Agent, saved work, and actions |
| Agent retrieve + real write | Twelve governed FastMCP tools read Gold/FDA context and write investigations, notes, follow-ups, and statuses |

The upstream assignment requirements are documented at <https://github.com/EcZachly/databricks-ai-bootcamp-capstone>.

## Data sources and default scope

- [CMS State Drug Utilization Data 2024](https://data.medicaid.gov/dataset/61729e5a-7aa8-448c-8903-ba3e0cd0ea3c), dataset `61729e5a-7aa8-448c-8903-ba3e0cd0ea3c`
- [CMS State Drug Utilization Data 2025](https://data.medicaid.gov/dataset/158a1baa-5506-400a-8ec3-97756f0b0536), dataset `158a1baa-5506-400a-8ec3-97756f0b0536`
- [CMS Open Data API](https://data.medicaid.gov/about/api)
- [openFDA NDC](https://open.fda.gov/apis/drug/ndc/) and [Drug Label](https://open.fda.gov/apis/drug/label/)

Default analysis is intentionally bounded to 2024–2025 and CA, TX, NY, FL, and IL. `MEDICAID_STATES` can expand later. Only the top 50 products by reimbursement across the selected scope are submitted for openFDA enrichment. No synthetic reimbursement records are generated or required.

### CMS ingestion modes

`CMS_MODE=api` is preferred. `cms_medicaid_client.py` uses the official datastore route, one state/year dataset at a time, with indexed state conditions, bounded `limit`/`offset`, timeouts, and retries for 429/5xx. Each page is written to Delta before the next page is requested; annual data is never accumulated in Python memory.

`CMS_MODE=bulk_csv` is the reliable fallback. It streams each official annual CSV through `csv.DictReader`, keeps only configured states, and passes bounded batches to Spark. It never reads the complete annual file into driver memory. The public URLs are encoded in `config/project_config.py`; source data is deliberately excluded from the repository and submission ZIP.

Bronze record hashes make reruns idempotent. The staging table is merged only after the requested source pass succeeds.

## Medallion pipeline and analytical model

1. `01_ingest_medicaid.py` preserves raw source strings plus source year, dataset identifier, mode, URL, ingestion time, and deterministic record hash in `bronze_raw_medicaid_utilization`.
2. `02_transform_silver.py` normalizes NDC11 and its segments, types amounts/counts, builds `product_key` from labeler+product segments, and writes `silver_medicaid_utilization_clean`.
3. `03_build_gold.py` excludes suppressed/missing quantitative rows from sums while retaining them in Silver, then materializes:
   - `gold_drug_performance_quarterly` at year/quarter/state/utilization type/product grain;
   - `gold_drug_performance_yoy` for identical-quarter 2025-versus-2024 comparisons;
   - `gold_state_performance` for compact state/utilization KPIs;
   - `gold_portfolio_summary` for compact portfolio KPIs.
4. `04_enrich_openfda.py` selects at most 50 products, attempts deterministic package-NDC forms, persists match status/method, metadata, and available label sections.
5. `05_ingest_drug_embeddings.py` embeds only new/content-changed documents.

All stages are sequential, the Job is manually triggered, and `max_concurrent_runs` is one. The frontend never reruns Spark.

### Suppression behavior

Silver preserves `suppression_used`. Suppressed/missing money, prescription, and unit values remain null; they are never coerced to zero. Gold quantitative calculations include only non-suppressed rows with available reimbursement. The agent prompt explicitly prevents claims that suppression means zero.

### Exact reimbursement decomposition

For prior/current prescription volumes `V0`, `V1` and reimbursement-per-prescription rates `R0`, `R1`:

```text
volume_effect = (V1 - V0) * ((R0 + R1) / 2)
rate_mix_effect = (R1 - R0) * ((V0 + V1) / 2)
```

The symmetric effects exactly reconcile to `V1*R1 - V0*R0`, apart from decimal rounding. The second component is called reimbursement-per-prescription or rate/mix effect—not pharmaceutical price. Unit tests enforce reconciliation across positive, negative, and zero-prior examples.

## openFDA matching and unstructured retrieval

CMS uses 11-digit billing NDCs. `pipeline/ndc_utils.py` splits the padded 5-4-2 form and generates only structurally valid historical FDA 4-4-2, 5-3-2, and 5-4-1 candidates by removing a leading zero from the appropriate segment. Exact package matching is attempted first; a constrained brand-name fallback is marked `fallback`, never exact. Unmatched products remain explicit and no metadata is fabricated.

Available label sections are normalized into one provenance-rich document: product, names, section names, narrative, source identifier, original payload, SHA-256 content hash, and synchronization time. Chunking defaults to 800 characters with 100-character overlap. `sentence-transformers/all-MiniLM-L6-v2` produces normalized 384-dimensional embeddings stored in Lakebase `VECTOR(384)` with an HNSW cosine index. Changed hashes rebuild a document's chunks; unchanged content is skipped. No AI Search endpoint or GPU is needed.

## Governed MCP tools

| Tool | Purpose |
|---|---|
| `get_market_overview` | Scoped KPIs, YoY result, top products |
| `get_product_performance` | Named-product metrics, comparison, and trend |
| `get_variance_drivers` | Positive/negative contributors by governed dimension |
| `decompose_reimbursement_change` | Exact volume and reimbursement-per-prescription effects |
| `detect_reimbursement_outliers` | Transparent 1.5×IQR flags |
| `get_drug_profile` | Structured matched openFDA profile |
| `search_drug_context` | FDA-label semantic chunks and similarity |
| `save_investigation` | Explicitly requested investigation/finding persistence |
| `add_analyst_note` | Explicit operational note |
| `create_follow_up_action` | Explicit linked follow-up |
| `update_investigation_status` | Open/completed/archived workflow status |
| `update_follow_up_action` | Open/completed/cancelled action status |

Every tool has selection guidance and limitations in its FastMCP docstring. Application code owns every SQL statement. User arguments are bound as parameters, identifier/metric/dimension choices are allow-listed, and there is no arbitrary SQL tool.

## Frontend

The single frontend App provides management-facing KPI cards, positive/negative YoY movers, a prominent “Ask Pharma Finance” Agent panel, saved investigations, follow-up actions, and a basic action-completion control. It attaches the Agent endpoint, SQL Warehouse, and existing Lakebase database through managed App resources and uses `WorkspaceClient()` authentication. It does not contain fixed answers or analytical writes.

## Free Edition resource design

The design reflects the current [Databricks Free Edition limitations](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations): one existing SQL Warehouse, one existing Lakebase project, and at most three Apps account-wide. This capstone consumes exactly two Apps:

1. `mcp-pharma-intelligence`
2. `pharma-finance-intelligence`

It creates no new Lakebase project, AI Search endpoint, GPU endpoint, monitoring App, uncontrolled schedule, full-history scan, or per-request Spark work. If three old bootcamp Apps already exist, remove or stop an old App before adding these two. Apps may need restarting after the Free Edition runtime window.

## Deployment

### 1. Prerequisites

- Authenticate the Databricks CLI/VS Code extension to the target workspace.
- Reuse the existing Free Edition SQL Warehouse and existing Lakebase Autoscaling project/database.
- Ensure pgvector is enabled in that database.
- Choose an existing Unity Catalog catalog and grant the pipeline identity permission to create/use the capstone schema/tables.
- Ensure serverless Job outbound access can reach `data.medicaid.gov`, `download.medicaid.gov`, `api.fda.gov`, and the model download host. If CMS outbound access is blocked, manually place the official file in an allowed location or run the documented streaming fallback from an environment with access; never replace it with synthetic data.

### 2. Configure and deploy the manual Job

The final two tasks accept the existing Lakebase endpoint resource name as a runtime Job parameter. The code obtains the endpoint host and current Job identity through the Databricks SDK, then generates a short-lived OAuth credential. No PostgreSQL host, user, password, or OAuth token is committed.

```bash
databricks bundle validate -t dev
databricks bundle deploy -t dev
databricks bundle run -t dev pharma_intelligence_pipeline -- \
  --lakebase_endpoint_name="projects/<project>/branches/<branch>/endpoints/<endpoint>"
```

Alternatively, open the deployed Job, select **Run now with different settings**, and set `lakebase_endpoint_name`; `lakebase_database` defaults to `databricks_postgres`. Use the endpoint's full resource name from Lakebase **Computes > Get ID > Copy resource name**. The Job's **Run as** identity must have an OAuth Postgres role and permission to inspect that endpoint.

Use `--var="cms_mode=bulk_csv"` only for the fallback. Run once initially; there is no schedule. Inspect counts, suppression nulls, representative Gold metrics, openFDA match statuses, document counts, embedding counts, and decomposition reconciliation before App deployment.

### 3. Database permissions

Reuse the existing Lakebase project. Create only the `pharma_intelligence` schema/tables via the pipeline's idempotent initialization. Grant the MCP App identity access to that schema for document reads and operational DML; grant the frontend identity read access plus update permission only on follow-up action status if using the completion button. Do not configure a static database password.

### 4. SQL Warehouse and Unity Catalog permissions

Reuse the existing Warehouse. Attach it with **Can use** (not Can manage). Grant both Apps `USE CATALOG`, `USE SCHEMA`, and `SELECT` on the four Gold tables. Neither App needs Gold INSERT/UPDATE/DELETE/MODIFY privileges.

### 5. Deploy MCP App

Create `mcp-pharma-intelligence` with source directory `mcp_server/`.

| Resource | Key | Permission |
|---|---|---|
| Existing Lakebase database | `postgres` | Can connect and create/use dedicated schema |
| Existing SQL Warehouse | `sql-warehouse` | Can use |

Set `CATALOG`/`SCHEMA` in `mcp_server/app.yaml` if your names differ, deploy, then verify the streamable endpoint at `<app-url>/mcp`. The App receives `PG*` values and `ENDPOINT_NAME` from the database resource and generates a fresh OAuth credential per connection.

### 6. Configure Agent Bricks

Follow `agent/setup.md`: register/select the MCP App, enable the twelve tools, paste `agent/system_prompt.md`, run `agent/demo_questions.md`, and deploy the Agent endpoint. Confirm the write demo returns an investigation UUID and linked follow-up UUID. This repository does not claim the external Agent was registered or deployed locally.

### 7. Deploy frontend App

Create `pharma-finance-intelligence` with source directory `frontend/`.

| Resource | Key | Permission |
|---|---|---|
| Deployed Agent endpoint | `finance-agent` | Can query |
| Existing Lakebase database | `postgres` | Connect/read; limited follow-up update |
| Existing SQL Warehouse | `sql-warehouse` | Can use |

Update frontend catalog/schema environment values if needed, deploy, verify `/health`, load KPIs, ask a demo question, save through the agent, and refresh the workspace panels.

## Security

- No workspace URL, warehouse ID, endpoint ID, credential, openFDA key value, database password, client secret, or personal access credential is committed.
- App resources inject runtime identifiers. `WorkspaceClient()` handles App identity authentication.
- Lakebase uses `generate_database_credential`; Jobs derive host/user metadata from the endpoint and run identity, while Apps receive `PG*` settings from attached resources. No credential-bearing database URL exists.
- `OPENFDA_API_KEY` is optional and absent by default. If used, inject it through secure Databricks runtime configuration/secret handling.
- Agent operational tables are isolated from analytical facts. Least-privilege grants enforce the boundary in addition to tool design.
- Logs and user errors do not disclose internal exception details.

## Local verification

Tests use mocks and require no live CMS, openFDA, Databricks, Lakebase, SQL Warehouse, or model download:

```bash
python -m compileall .
pytest -q
python scripts/smoke_test.py
```

Bundle schema can be checked with `databricks bundle validate`; workspace resolution additionally requires configured Databricks authentication.

## Limitations

- Default analysis covers five selected states and two years, not a national or long-term market view.
- CMS suppression makes some values unavailable; exclusion reduces comparability and suppressed values are never interpreted as zero.
- CMS reimbursement is not manufacturer sales, and reimbursement per prescription is not list/net price.
- FDA native/package NDC reconciliation is imperfect; fallback and unmatched status must be considered.
- Drug labels vary in available sections and openFDA content can change.
- Semantic similarity retrieves context; it does not validate clinical truth or provide medical advice.
- Two years support identical-quarter YoY comparison, not forecasting or long-term causal inference.
- Free Edition has constrained compute, outbound access, App runtime, and no SLA. Run the bounded pipeline intentionally and monitor it.
- Public data cannot reveal confidential rebates, contracting terms, gross-to-net adjustments, company sales, or profit.

## Future production evolution

An enterprise version could replace public CMS Gold tables with governed internal Finance, gross-to-net, contracting, demand, channel, and market-access semantic models while retaining the same Spark medallion structure, compact Gold contract, purpose-built MCP tools, Agent guardrails, Lakebase operational state, and frontend. Production evolution would add formal data contracts, quality SLAs, identity-level row/column policies, lineage/monitoring, approved enterprise embedding/model endpoints, human approval for consequential actions, and validated causal methods. Public CMS would remain an external benchmark, not a substitute for company financials.

## Submission ZIP

Build the source-only archive from the repository root:

```bash
python scripts/build_submission_zip.py
```

The script uses an allow-list and excludes Git metadata, environments, caches, editor files, logs, screenshots, generated ZIPs, raw CSVs, Parquet/Delta data, and model caches. The archive contains one top-level `pharma-market-financial-intelligence-capstone/` directory with the deployable source and documentation only.
