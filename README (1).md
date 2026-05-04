# Snowflake Starter Kit for VS Code + GitHub Copilot

A complete, production-ready starter project for working with Snowflake. Optimized for AI-assisted development with GitHub Copilot, Claude Code, or any LLM-powered IDE.

## What's Included

### Core
- 🔌 **Snowflake connectors** — Python connector and Snowpark with key-pair, password, and SSO auth
- 🗄️ **SQL templates** — DDL, DML, queries, procedures, and migrations
- 🔧 **VS Code config** — extensions, settings, tasks, debug configs
- 🧪 **Tests** — pytest with mocking patterns and integration markers
- 📓 **Notebooks** — Jupyter examples
- 🔐 **Secure config** — `.env` patterns, key-pair generation script
- 🚀 **CI/CD** — GitHub Actions for PR validation and prod deploys

### AI assistance
- 🤖 **Copilot instructions** — `.github/copilot-instructions.md` loaded automatically
- 💬 **Custom prompts** — `.github/prompts/` for new tables, procedures, optimization, tests
- 🎯 **Chat modes** — DBA, analytics engineer, FinOps personas
- 📚 **Skills** — Six domain-expert knowledge packs (`skills/`)
- 🧑‍💻 **Agents** — Six task-focused agents (`agents/`)
- 📐 **Path-scoped instructions** — Targeted Copilot rules for SQL and Python files (`.github/instructions/`)
- 🧠 **Claude Code** — `CLAUDE.md` memory file and `.claude/commands/` slash commands

### Boilerplates
- 📊 **dbt** — full project with sources, models, snapshots, macros
- 📈 **Streamlit** — dashboard app with local + Streamlit-in-Snowflake support
- 🌬️ **Airflow** — DAGs for loads, dbt runs, data quality, cost monitoring
- 🐍 **Snowpark app** — procedures, UDFs, deploy scripts, tests
- ✅ **Data quality** — declarative YAML check framework with runner
- 🔄 **CI/CD** — PR validation, CI deploy, prod deploy with approvals

## Quick Start

```bash
# 1. Install
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure
cp .env.example .env  # then edit

# 3. Verify
python python/connectors/test_connection.py
```

Open the folder in VS Code, accept the recommended extensions, and you're ready.

## Project Bootstrap

If you're scaffolding the directory layout from scratch (without unzipping the kit), this single command creates every directory the kit expects:

```bash
mkdir -p snowflake-starter-kit/{.claude/commands,.github/{prompts,chatmodes,instructions,workflows},.vscode,agents/{etl-pipeline-builder,query-optimizer,schema-migrator,data-quality-guardian,test-data-factory,docs-writer},skills/{snowflake-sql-author,snowflake-performance-tuner,snowflake-security-auditor,snowflake-cost-optimizer,snowflake-data-modeler,snowflake-notebook-author},boilerplates/{dbt/{macros,models/{staging,intermediate,marts},seeds,snapshots,tests},streamlit/pages,airflow/dags,snowpark-app/{deploy,src/{lib,procedures,udfs},tests},data-quality/checks,cicd},workflows/frongello-attribution/{spec,prompts,reference,implementation,tests},templates/{sql,python,yaml},sql/{ddl,dml,queries,procedures,migrations},python/{connectors,etl,utils},notebooks,tests,scripts,config,docs/{adr,models,onboarding}}
```

Or, if you prefer it readable across multiple lines:

```bash
mkdir -p snowflake-starter-kit/.claude/commands
mkdir -p snowflake-starter-kit/.github/{prompts,chatmodes,instructions,workflows}
mkdir -p snowflake-starter-kit/.vscode

# AI assistance
mkdir -p snowflake-starter-kit/agents/{etl-pipeline-builder,query-optimizer,schema-migrator,data-quality-guardian,test-data-factory,docs-writer}
mkdir -p snowflake-starter-kit/skills/{snowflake-sql-author,snowflake-performance-tuner,snowflake-security-auditor,snowflake-cost-optimizer,snowflake-data-modeler,snowflake-notebook-author}

# Boilerplates
mkdir -p snowflake-starter-kit/boilerplates/dbt/{macros,models/{staging,intermediate,marts},seeds,snapshots,tests}
mkdir -p snowflake-starter-kit/boilerplates/streamlit/pages
mkdir -p snowflake-starter-kit/boilerplates/airflow/dags
mkdir -p snowflake-starter-kit/boilerplates/snowpark-app/{deploy,src/{lib,procedures,udfs},tests}
mkdir -p snowflake-starter-kit/boilerplates/data-quality/checks
mkdir -p snowflake-starter-kit/boilerplates/cicd

# Vibe-coding workflows
mkdir -p snowflake-starter-kit/workflows/frongello-attribution/{spec,prompts,reference,implementation,tests}

# Templates and project code
mkdir -p snowflake-starter-kit/templates/{sql,python,yaml}
mkdir -p snowflake-starter-kit/sql/{ddl,dml,queries,procedures,migrations}
mkdir -p snowflake-starter-kit/python/{connectors,etl,utils}
mkdir -p snowflake-starter-kit/{notebooks,tests,scripts,config}
mkdir -p snowflake-starter-kit/docs/{adr,models,onboarding}
```

The `-p` flag matters: it creates parent directories as needed and won't error if any already exist.

⚠️ **Bash or Zsh required for the one-liner.** The nested brace expansion `{a,{b,c}}` is a Bash/Zsh feature; POSIX `sh` and `dash` will silently create directories with literal braces in the name. Either run it explicitly under bash:

```bash
bash -c 'mkdir -p snowflake-starter-kit/{...}'
```

or use the multi-line version above (which also works in any shell, since it doesn't rely on nested braces).

To verify the layout was created correctly, run `find snowflake-starter-kit -type d | wc -l` — it should report **76 directories**.

### Or use the bootstrap script

The kit ships with `scripts/bootstrap_directories.sh` which does all of the above and verifies the directory count:

```bash
./scripts/bootstrap_directories.sh                          # creates ./snowflake-starter-kit
./scripts/bootstrap_directories.sh /path/to/my-project      # creates at the given path
```

The script is idempotent — safe to re-run, never overwrites existing files.

## Project Structure

```
snowflake-starter-kit/
├── .claude/
│   └── commands/              # Claude Code slash commands
├── .github/
│   ├── copilot-instructions.md
│   ├── prompts/               # Reusable Copilot prompts
│   ├── chatmodes/             # Custom chat personas
│   ├── instructions/          # Path-scoped Copilot rules
│   └── workflows/             # GitHub Actions
├── .vscode/                   # IDE config
├── CLAUDE.md                  # Claude Code project memory
├── agents/                    # Task-focused AI agents
│   ├── etl-pipeline-builder/
│   ├── query-optimizer/
│   ├── schema-migrator/
│   ├── data-quality-guardian/
│   ├── test-data-factory/
│   └── docs-writer/
├── skills/                    # Domain-expert knowledge packs
│   ├── snowflake-sql-author/
│   ├── snowflake-performance-tuner/
│   ├── snowflake-security-auditor/
│   ├── snowflake-cost-optimizer/
│   ├── snowflake-data-modeler/
│   └── snowflake-notebook-author/
├── boilerplates/              # Drop-in mini-projects
│   ├── dbt/
│   ├── streamlit/
│   ├── airflow/
│   ├── snowpark-app/
│   ├── data-quality/
│   └── cicd/
├── workflows/                 # Vibe-coding playbooks for specific algorithms
│   └── frongello-attribution/
│       ├── spec/              # Charter, formula, interface
│       ├── prompts/           # Phase-by-phase AI prompts
│       ├── reference/         # Worked examples, citations
│       ├── implementation/    # Python, Snowpark, SQL versions
│       ├── tests/             # Pytest cases
│       └── index.html         # Interactive reference + calculator
├── templates/                 # File templates for new objects
│   ├── sql/
│   ├── python/
│   └── yaml/
├── sql/
│   ├── ddl/                   # Tables, schemas, audit log
│   ├── dml/                   # Inserts, updates, merges
│   ├── queries/               # Analytical queries
│   ├── procedures/            # Stored procs and UDFs
│   └── migrations/            # Versioned schema changes
├── python/
│   ├── connectors/            # Connection helpers
│   ├── etl/                   # Pipeline code
│   └── utils/                 # Shared utilities
├── notebooks/                 # Jupyter examples
├── tests/                     # Pytest suite
├── scripts/                   # Setup and admin scripts
└── docs/                      # Architecture, Copilot guide, ADRs, models
```

## Skills

Each skill is a markdown file with frontmatter that AI assistants read on-demand to specialize their behavior for a domain.

| Skill                              | Use for                                                |
|------------------------------------|--------------------------------------------------------|
| `snowflake-sql-author`             | Writing SQL — formatting, naming, idempotency          |
| `snowflake-performance-tuner`      | Diagnosing and fixing slow queries                     |
| `snowflake-security-auditor`       | RBAC, masking, network policies, key-pair auth         |
| `snowflake-cost-optimizer`         | Credit reviews, FinOps, warehouse right-sizing         |
| `snowflake-data-modeler`           | Star schemas, SCD, grain decisions                     |
| `snowflake-notebook-author`        | Jupyter / Snowflake notebooks for analysis             |

## Agents

Each agent is a complete task playbook for AI assistants — input requirements, workflow, output spec, and quality bar.

| Agent                        | Triggers when you ask to...                       |
|------------------------------|---------------------------------------------------|
| `etl-pipeline-builder`       | Build an end-to-end source-to-mart pipeline       |
| `query-optimizer`            | Diagnose and rewrite a slow query                 |
| `schema-migrator`            | Generate safe forward/rollback migrations         |
| `data-quality-guardian`      | Generate a test suite for a table                 |
| `test-data-factory`          | Generate realistic synthetic test data            |
| `docs-writer`                | Write or update model docs, runbooks, ADRs       |

## Custom prompts (Copilot Chat slash commands)

| Prompt              | Purpose                                        |
|---------------------|------------------------------------------------|
| `/new-table`        | Generate a Snowflake table DDL                 |
| `/new-procedure`    | Scaffold a stored procedure                    |
| `/optimize-query`   | Analyze and improve a slow query               |
| `/generate-test`    | Create pytest tests for code                   |

## Chat modes

Switch Copilot's persona for different tasks. In Copilot Chat, select a mode from the dropdown.

| Mode                  | Use for                                       |
|-----------------------|-----------------------------------------------|
| `snowflake-dba`       | Schema, security, platform tasks              |
| `analytics-engineer`  | Modeling, transforms, BI work                 |
| `finops`              | Cost reviews, warehouse tuning                |

## Claude Code commands

If you use Claude Code, these slash commands are available:

| Command          | Action                                              |
|------------------|-----------------------------------------------------|
| `/new-model`     | Scaffold a complete new fact or dimension           |
| `/migrate`       | Generate a versioned schema migration               |
| `/optimize`      | Diagnose and rewrite a slow query                   |
| `/cost-review`   | Run a Snowflake cost analysis report                |

## Boilerplates

Drop-in mini-projects you can copy and adapt. Each has its own README.

| Boilerplate         | What you get                                                |
|---------------------|-------------------------------------------------------------|
| `dbt/`              | Full dbt project: sources, staging, marts, snapshots, tests |
| `streamlit/`        | Dashboard app — works locally and as Streamlit-in-Snowflake |
| `airflow/`          | DAGs for loads, dbt, data quality, cost monitoring          |
| `snowpark-app/`     | Snowpark Python procedures + UDFs with deploy scripts       |
| `data-quality/`     | Declarative YAML check framework + runner                   |
| `cicd/`             | GitHub Actions workflows for PR + prod deploys              |

## Authentication Methods

1. **Username/password** — Quick start (dev only)
2. **Key-pair authentication** — Recommended for production (run `scripts/generate_key_pair.sh`)
3. **SSO/External browser** — For interactive use
4. **OAuth** — For applications

## License

MIT — Use this freely as a template for your team.

## Contributing

This kit is meant to be forked and adapted. The skills, agents, and boilerplates are deliberately opinionated to give AI assistants strong defaults. Override anything that doesn't match your team's conventions.
