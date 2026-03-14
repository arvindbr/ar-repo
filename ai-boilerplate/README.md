# AI Boilerplate — MCP + Snowflake + Azure + OpenAI Agents

A production-ready boilerplate for building AI agent applications with:

- **MCP Server** — Model Context Protocol server exposing Snowflake as a tool backend
- **OpenAI Agent** — Agents SDK agent that calls the MCP server for data retrieval
- **Azure Container Apps** — Deployment infra (Bicep + Dockerfile)

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Client / API                        │
└──────────────────────┬──────────────────────────────────┘
                       │
           ┌───────────▼───────────┐
           │   OpenAI Agent (SDK)  │
           │  GPT-4o + tool calls  │
           └───────────┬───────────┘
                       │  MCP calls
           ┌───────────▼───────────┐
           │     MCP Server        │
           │  (FastAPI / SSE)      │
           └───────────┬───────────┘
                       │  SQL
           ┌───────────▼───────────┐
           │      Snowflake        │
           │  (Connector Python)   │
           └───────────────────────┘

Both services run as Azure Container Apps
Secrets managed via Azure Key Vault
```

---

## Project Structure

```
.
├── mcp-server/          # MCP server (FastAPI + Snowflake)
│   ├── main.py
│   ├── tools/
│   │   └── snowflake_tools.py
│   ├── Dockerfile
│   └── requirements.txt
│
├── agent/               # OpenAI Agents SDK agent
│   ├── main.py
│   ├── agent.py
│   ├── Dockerfile
│   └── requirements.txt
│
├── infra/
│   ├── azure/
│   │   └── main.bicep   # Azure Container Apps + Key Vault
│   └── docker/
│       └── docker-compose.yml
│
├── shared/
│   └── config.py        # Shared Pydantic settings
│
└── .env.example
```

---

## Quick Start

### 1. Clone & configure

```bash
cp .env.example .env
# Fill in Snowflake + Azure + OpenAI credentials
```

### 2. Run locally with Docker Compose

```bash
docker-compose -f infra/docker/docker-compose.yml up --build
```

Services:
- MCP Server → http://localhost:8001
- Agent API  → http://localhost:8000

### 3. Deploy to Azure

```bash
az login
az deployment group create \
  --resource-group my-rg \
  --template-file infra/azure/main.bicep \
  --parameters @infra/azure/parameters.json
```

---

## Environment Variables

| Variable | Description |
|---|---|
| `SNOWFLAKE_ACCOUNT` | e.g. `xy12345.us-east-1` |
| `SNOWFLAKE_USER` | Snowflake username |
| `SNOWFLAKE_PASSWORD` | Snowflake password |
| `SNOWFLAKE_WAREHOUSE` | Compute warehouse |
| `SNOWFLAKE_DATABASE` | Target database |
| `SNOWFLAKE_SCHEMA` | Target schema |
| `SNOWFLAKE_ROLE` | Optional role |
| `OPENAI_API_KEY` | OpenAI API key |
| `MCP_SERVER_URL` | MCP SSE endpoint (e.g. `http://mcp-server:8001/sse`) |
| `AZURE_KEY_VAULT_URL` | Key Vault URI (prod only) |
