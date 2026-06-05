# tf_differ — Terraform Plan Diff HTML Dashboard

> Cloud Agnostic · Risk Aware · Interactive Dashboard · FinOps Cost Tracking

Generates a self-contained HTML report from a Terraform plan file. Shows every resource change with risk scoring, cost impact (via Infracost), dependency analysis, JSON diffs, and an optional AI architecture review (via Ollama).

---

## Features

- **Supports binary `.tfplan` and JSON plan files** — auto-detects format
- **Risk scoring** — classifies each change as critical / high / medium / low based on action type and resource keywords
- **Resource categorisation** — groups resources into security, network, compute, database, container, storage
- **Dependency mapping** — shows which resources are affected downstream by each change
- **Cost analysis** — integrates with Infracost to show monthly cost delta per resource
- **JSON diff viewer** — side-by-side before/after for updates and replacements
- **AI architecture review** — sends changes to a local Ollama LLM for security and risk commentary
- **Searchable HTML report** — filterable table, no external dependencies at runtime

---

## Requirements

### Python packages

```bash
pip install requests markdown
```

| Package    | Purpose                              | Required |
|------------|--------------------------------------|----------|
| `requests` | LLM calls to Ollama                  | Yes      |
| `markdown` | Renders LLM output in HTML           | Optional |

All other imports (`json`, `difflib`, `argparse`, `pathlib`, etc.) are Python standard library.

### External CLI tools

| Tool          | Purpose                                      | Required |
|---------------|----------------------------------------------|----------|
| `terraform`   | Convert binary `.tfplan` → JSON              | Only for binary plans |
| `infracost`   | Cost impact per resource                     | Optional |
| `ollama`      | Local LLM for AI architecture review         | Optional |

---

## Installation

```bash
git clone <your-repo>
cd tf_differ
pip install requests markdown
```

---

## Usage

```bash
# Basic — binary plan
python3 tf_differ.py --plan-file tfplan.binary --terraform-dir .

# Basic — JSON plan (no terraform binary needed)
python3 tf_differ.py --plan-file plan.json --terraform-dir .

# Custom output file
python3 tf_differ.py --plan-file tfplan.binary --terraform-dir . --output my-report.html

# Skip LLM analysis (faster)
python3 tf_differ.py --plan-file tfplan.binary --terraform-dir . --no-llm

# Use a different Ollama model
python3 tf_differ.py --plan-file tfplan.binary --terraform-dir . --llm-model mistral

# Save logs to file with verbose output
python3 tf_differ.py --plan-file tfplan.binary --terraform-dir . --log-file run.log --verbose
```

### All flags

| Flag              | Default                        | Description                                      |
|-------------------|--------------------------------|--------------------------------------------------|
| `--plan-file`     | `plan.json`                    | Path to `.tfplan` (binary) or `.json` plan file  |
| `--terraform-dir` | `.`                            | Terraform working directory (for binary plans)   |
| `--output`        | `terraform-plan-report.html`   | Output HTML report file name                     |
| `--no-llm`        | off                            | Disable Ollama LLM analysis                      |
| `--llm-model`     | `llama3.1`                     | Ollama model to use                              |
| `--ollama-url`    | `http://localhost:11434`       | Ollama service URL                               |
| `--log-file`      | None                           | Optional path to write logs                      |
| `--verbose`       | off                            | Enable DEBUG level logging                       |

---

## Project Structure

```
tf_differ/
├── tf_differ.py              # Main entry point — orchestrates the pipeline
└── scripts/
    ├── __init__.py           # Auto-discovers all modules in this package
    ├── logger.py             # Logging setup
    ├── config.py             # TerraformDiffConfig dataclass + CLI factory
    ├── risk_config.py        # RISK_RULES and HIGH_RISK_KEYWORDS constants
    ├── resource_mapper.py    # Dependency graph builder
    ├── plan_loader.py        # Loads JSON or binary plan files
    ├── cost_analyzer.py      # Infracost integration
    ├── change_extractor.py   # Extracts, risk-scores and categorises changes
    ├── llm_analyzer.py       # Ollama LLM architecture review
    └── html_reporter.py      # HTML dashboard generator
```

`tf_differ.py` contains no business logic — it only wires the pipeline together. All logic lives in `scripts/`.

---

## Adding a New Feature

1. Create `scripts/your_feature.py` with your function(s)
2. Import and call it in `tf_differ.py`
3. No changes to `__init__.py` needed — it auto-discovers everything

Example:

```python
# scripts/slack_notifier.py
def send_slack_notification(config, changes_data):
    ...
```

```python
# tf_differ.py  — inside run()
from scripts.slack_notifier import send_slack_notification
send_slack_notification(self.config, changes)
```

---

## Environment Variables

| Variable             | Purpose                                  |
|----------------------|------------------------------------------|
| `INFRACOST_API_KEY`  | Required for full Infracost cost details |

```bash
export INFRACOST_API_KEY=your_key_here
```

---

## Output

The report is a self-contained HTML file with no external dependencies. Open it in any browser:

```bash
open terraform-plan-report.html        # macOS
xdg-open terraform-plan-report.html   # Linux
start terraform-plan-report.html      # Windows
```

### What the report shows

- **Summary cards** — total changes, creates, updates, deletes, monthly cost delta
- **AI Architecture Review** — security risks, best practices, execution risks (if LLM enabled)
- **Searchable resource table** — filterable by any text in the table
  - Action badge with colour coding
  - Resource address and type
  - Provider and risk level
  - JSON diff (for updates/replacements)
  - Cost impact and breakdown
  - Dependent resources warning

---

## Risk Levels

| Level      | Colour | When assigned |
|------------|--------|---------------|
| `critical` | 🔴 Red    | Any delete, or delete of a high-risk resource |
| `high`     | 🟠 Orange | Update of a high-risk resource type |
| `medium`   | 🟡 Yellow | Create of a high-risk resource, or any create |
| `low`      | 🟢 Green  | Update of a standard resource |

High-risk resource keywords (defined in `scripts/risk_config.py`):
`iam`, `security`, `firewall`, `network`, `database`, `db`, `kubernetes`, `cluster`, `load_balancer`, `gateway`, `policy`, `role`, `vpn`, `proxy`, `vpc`

To add new keywords, edit `scripts/risk_config.py` only.

---

## Troubleshooting

**`terraform show` fails**
Make sure `terraform` is in your PATH and you have run `terraform init` in `--terraform-dir`.

**No cost data in report**
- Confirm `infracost` is installed: `infracost --version`
- Set `INFRACOST_API_KEY` environment variable
- Cost section is silently skipped if Infracost is unavailable

**LLM section missing**
- Confirm Ollama is running: `ollama serve`
- Check the model is pulled: `ollama pull llama3.1`
- Use `--no-llm` to skip entirely

**`ModuleNotFoundError: No module named 'scripts'`**
Run the script from inside the `tf_differ/` directory where `tf_differ.py` lives.

---

## License

MIT

