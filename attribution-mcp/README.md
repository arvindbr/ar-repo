# Attribution MCP Server

Production-ready multi-touch marketing attribution system built on the AI boilerplate.
Backed by **Snowflake**, served via **MCP over SSE**, reasoned over by an **OpenAI Agent**,
and deployed on **Azure Container Apps**.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Client / BI Dashboard                        │
└──────────────────────────┬──────────────────────────────────────┘
                           │  POST /query  (natural language)
               ┌───────────▼───────────┐
               │  Attribution Agent    │
               │  OpenAI gpt-4o        │
               │  Agents SDK           │
               └───────────┬───────────┘
                           │  MCP tool calls (SSE)
               ┌───────────▼───────────┐
               │  Attribution MCP      │
               │  Server (FastAPI)     │
               │                       │
               │  ┌─────────────────┐  │
               │  │ attribution_    │  │
               │  │ models.py       │  │  ← 6 attribution models
               │  ├─────────────────┤  │
               │  │ channel_        │  │
               │  │ performance.py  │  │  ← ROAS, spend, campaigns
               │  ├─────────────────┤  │
               │  │ conversion_     │  │
               │  │ paths.py        │  │  ← paths, funnel, TTC
               │  ├─────────────────┤  │
               │  │ incrementality  │  │
               │  │ .py             │  │  ← cohorts, overlap, lift
               │  └─────────────────┘  │
               └───────────┬───────────┘
                           │  SQL (read-only)
               ┌───────────▼───────────┐
               │       Snowflake       │
               │  TOUCHPOINTS          │
               │  CONVERSIONS          │
               │  SESSIONS             │
               │  CHANNEL_SPEND        │
               └───────────────────────┘
```

Both services deploy as **Azure Container Apps** with:
- Secrets in **Azure Key Vault** (accessed via Managed Identity — no stored creds)
- Images in **Azure Container Registry**
- Logs in **Log Analytics**

---

## MCP Tools — Full Reference

### Attribution Models (`attribution_models.py`)

| Tool | Description |
|---|---|
| `get_attribution` | Run one of 6 models for a date range and conversion event |
| `compare_attribution_models` | Side-by-side comparison of all 6 models |

**Supported models:**

| Model | Logic |
|---|---|
| `first_touch` | 100% credit to the first touchpoint |
| `last_touch` | 100% credit to the last touchpoint |
| `linear` | Equal credit split across all touches |
| `time_decay` | Exponential weight toward conversion (configurable half-life) |
| `position_based` | 40% first + 40% last + 20% distributed to middle |
| `data_driven` | Shapley value approximation (marginal contribution) |

### Channel Performance (`channel_performance.py`)

| Tool | Description |
|---|---|
| `get_channel_performance` | Sessions, conversions, revenue by channel/campaign/source |
| `get_channel_roas` | ROAS and CPA per channel vs. spend |
| `get_spend_trend` | Spend over time (daily/weekly/monthly) |
| `get_top_campaigns` | Top N campaigns ranked by revenue/conversions/ROAS |

### Conversion Paths (`conversion_paths.py`)

| Tool | Description |
|---|---|
| `get_top_conversion_paths` | Most common channel sequences before conversion |
| `get_path_length_distribution` | Distribution of journey lengths |
| `get_assisted_conversions` | Assisted vs. direct conversions per channel |
| `get_time_to_conversion` | Avg, median, p25/p75/p90 time-to-convert |

### Incrementality & Cohorts (`incrementality.py`)

| Tool | Description |
|---|---|
| `get_cohort_conversion_rate` | Conversion rates by acquisition cohort & channel |
| `get_channel_overlap` | Pairwise channel co-occurrence (synergy analysis) |
| `get_new_vs_returning_attribution` | Attribution split by new vs. returning users |

---

## Project Structure

```
attribution-mcp/
├── mcp-server/
│   ├── main.py                        # FastAPI + MCP SSE entrypoint
│   ├── tools/
│   │   ├── _db.py                     # Snowflake connection helper
│   │   ├── attribution_models.py      # 6 attribution models + comparison
│   │   ├── channel_performance.py     # ROAS, spend, top campaigns
│   │   ├── conversion_paths.py        # Path analysis, TTC, assisted
│   │   └── incrementality.py          # Cohorts, overlap, new vs returning
│   ├── Dockerfile
│   └── requirements.txt
│
├── agent/
│   ├── agent.py                       # OpenAI Agents SDK agent
│   ├── main.py                        # FastAPI API wrapper
│   ├── Dockerfile
│   └── requirements.txt
│
├── shared/
│   └── config.py                      # Pydantic settings (Snowflake + Attribution)
│
├── infra/
│   ├── snowflake_schema.sql           # DDL for all 4 attribution tables
│   ├── azure/
│   │   ├── main.bicep                 # Container Apps + Key Vault + ACR
│   │   └── parameters.json
│   └── docker/
│       └── docker-compose.yml
│
├── .env.example
└── README.md
```

---

## Quick Start

### 1. Provision Snowflake tables

```bash
snowsql -f infra/snowflake_schema.sql
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — fill in Snowflake creds and OpenAI key
```

### 3. Run locally

```bash
docker-compose -f infra/docker/docker-compose.yml up --build
```

| Service | URL |
|---|---|
| MCP Server | http://localhost:8001 |
| Agent API | http://localhost:8000 |
| MCP Tools list | http://localhost:8001/tools |
| Example questions | http://localhost:8000/examples |

### 4. Ask your first question

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"message": "Which channel has the best ROAS in Q1 2024?"}'
```

### 5. Deploy to Azure

```bash
az login
az group create --name my-attribution-rg --location eastus

az deployment group create \
  --resource-group my-attribution-rg \
  --template-file infra/azure/main.bicep \
  --parameters @infra/azure/parameters.json
```

---

## Example Questions

```
"Which channel has the highest ROAS this quarter?"
"Show me the top 10 conversion paths in January 2024."
"Compare all attribution models for the purchase event in Q4 2023."
"What percentage of Google Ads conversions were assisted by email?"
"How long does it take for paid social users to convert?"
"Which two channels have the most user overlap?"
"Break down conversions by new vs returning users per channel."
"Show me weekly spend trend for paid_search over the last 3 months."
"Which campaigns have the highest conversion rate?"
"How does linear attribution compare to last-touch for email?"
```

---

## Attribution Table Schema

```
TOUCHPOINTS        — one row per marketing touch (channel, campaign, user, time)
CONVERSIONS        — one row per conversion event (purchase, signup, lead...)
SESSIONS           — session enrichment (device, country, landing page)
CHANNEL_SPEND      — daily spend per channel/campaign for ROAS calculations
```

See `infra/snowflake_schema.sql` for full DDL with clustering keys and
search optimization.

---

## Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `ATTR_TOUCHPOINTS_TABLE` | `ATTRIBUTION.TOUCHPOINTS` | Touchpoints table FQN |
| `ATTR_CONVERSIONS_TABLE` | `ATTRIBUTION.CONVERSIONS` | Conversions table FQN |
| `ATTR_SPEND_TABLE` | `ATTRIBUTION.CHANNEL_SPEND` | Spend table FQN |
| `ATTR_LOOKBACK_DAYS` | `30` | Default touchpoint lookback window |
| `ATTR_TIME_DECAY_HALFLIFE` | `7.0` | Time-decay model half-life in days |
| `ATTR_DEFAULT_MODEL` | `linear` | Default model used in reports |
| `OPENAI_MODEL` | `gpt-4o` | OpenAI model for the agent |
