"""
scripts/html_reporter.py
Generates the interactive HTML dashboard from extracted Terraform changes.
"""

import difflib
import html
import json
from collections import Counter
from typing import Any, Dict

from scripts.config import TerraformDiffConfig
from scripts.logger import logger


def generate_diff_html(
    before: Dict | None,
    after: Dict | None,
) -> str:
    """
    Generate an HTML side-by-side diff between before and after states.

    Args:
        before: Before state dict (or None)
        after: After state dict (or None)

    Returns:
        HTML formatted diff table
    """
    before_str = json.dumps(before, indent=2).splitlines() if before else []
    after_str = json.dumps(after, indent=2).splitlines() if after else []
    differ = difflib.HtmlDiff(wrapcolumn=80)

    return differ.make_table(
        before_str,
        after_str,
        fromdesc="Before",
        todesc="After",
        context=True,
        numlines=3,
    )


def generate_html_report(
    config: TerraformDiffConfig,
    changes_data: Dict[str, Any],
    llm_explanation: str = "",
) -> str:
    """
    Generate complete HTML report with changes and optional LLM analysis.

    Args:
        config: Active TerraformDiffConfig (provides color maps and row cap)
        changes_data: Dictionary with extracted changes (from change_extractor)
        llm_explanation: LLM analysis text (optional)

    Returns:
        HTML content as string
    """
    logger.info("Generating HTML report...")

    action_colors = config.COLORS
    risk_colors = config.RISK_COLORS
    action_icons = {
        "create": "+",
        "update": "~",
        "delete": "-",
        "replace": "⇄",
    }

    all_changes = changes_data["changes"]
    visible_changes = all_changes[: config.max_table_rows]

    # Risk composition (drives the risk strip signature element)
    risk_counter = Counter(str(c.get("risk", "unknown")) for c in all_changes)
    total_risk_count = sum(risk_counter.values()) or 1
    risk_order = sorted(risk_counter.items(), key=lambda kv: kv[1], reverse=True)
    risk_segments = "".join(
        f'<div class="risk-seg" style="width:{(count / total_risk_count) * 100:.3f}%;'
        f'background:{risk_colors.get(risk, "#5b6472")};" '
        f'title="{html.escape(risk)}: {count}"></div>'
        for risk, count in risk_order
    )
    risk_legend = "".join(
        f'<span class="risk-legend-item"><i style="background:{risk_colors.get(risk, "#5b6472")};"></i>'
        f'{html.escape(risk)} · {count}</span>'
        for risk, count in risk_order
    )

    high_risk_count = sum(
        1 for c in all_changes if str(c.get("risk", "")).strip().lower() == "high"
    )
    provider_count = len({c.get("provider", "") for c in all_changes if c.get("provider")})
    total_monthly_cost = sum(
        c.get("costs", {}).get("monthly_cost", 0.0) or 0.0 for c in all_changes
    )

    changes_rows = []

    for change in visible_changes:
        action = change["action"]
        color = action_colors.get(action, "#6c757d")
        icon = action_icons.get(action, "•")

        costs = change.get("costs", {})
        components = costs.get("components", [])
        diff_cost = costs.get("diff_cost", 0.0)
        monthly_cost = costs.get("monthly_cost", 0.0)

        address_escaped = html.escape(change["address"])
        type_escaped = html.escape(change["type"])
        provider_escaped = html.escape(change["provider"])
        category_escaped = html.escape(change["category"])
        risk_escaped = html.escape(change["risk"])
        risk_attr = html.escape(str(change["risk"]).lower())
        action_attr = html.escape(str(action).lower())

        diff_html = ""
        cost_str = ""
        component_html = ""
        affected_str = ""

        if action in ["update", "replace"] and change["before"] and change["after"]:
            diff_html = f"""
            <details>
                <summary class="detail-toggle">View JSON diff</summary>
                <div class="diff-wrap">{generate_diff_html(change["before"], change["after"])}</div>
            </details>
            """

        if monthly_cost > 0 or diff_cost != 0:
            cost_class = "cost-up" if diff_cost > 0 else "cost-down" if diff_cost < 0 else "cost-flat"
            sign = "+" if diff_cost > 0 else ""
            cost_str = f"""
            <div class="cost-badge {cost_class}">
                <span class="cost-badge-label">Cost impact</span>
                <span class="cost-badge-value">{sign}${diff_cost:.2f}/mo</span>
                <span class="cost-badge-total">total ${monthly_cost:.2f}/mo</span>
            </div>
            """

        if components:
            component_rows = "".join(
                f"""
                <tr>
                    <td>{html.escape(c.get("name", "Unknown"))}</td>
                    <td class="mono">${c.get("monthlyCost", "0")}</td>
                </tr>
                """
                for c in components
            )
            component_html = f"""
            <details class="detail-block">
                <summary class="detail-toggle detail-toggle--sub">Cost breakdown</summary>
                <table class="mini-table">
                    {component_rows}
                </table>
            </details>
            """

        if change.get("affected_resources"):
            affected_list = "".join(
                f"<li>{html.escape(r)}</li>" for r in change["affected_resources"][:5]
            )
            affected_str = f"""
            <details class="detail-block">
                <summary class="detail-toggle detail-toggle--warn">{len(change['affected_resources'])} dependent resources</summary>
                <div class="affected-box">
                    <ul>{affected_list}</ul>
                </div>
            </details>
            """

        changes_rows.append(f"""
        <tr data-action="{action_attr}" data-risk="{risk_attr}">
            <td class="col-action" style="color:{color};">
                <span class="action-icon" style="background:{color}22;color:{color};">{icon}</span>
                {html.escape(action.upper())}
            </td>
            <td class="col-address mono">{address_escaped}</td>
            <td class="col-type">
                {type_escaped}
                <span class="chip chip-neutral">{category_escaped}</span>
            </td>
            <td class="col-provider">
                {provider_escaped}
                <span class="chip" style="background:{risk_colors.get(change['risk'], '#6c757d')};">{risk_escaped}</span>
            </td>
            <td class="col-impact">{diff_html}{cost_str}{component_html}{affected_str}</td>
        </tr>
        """)

    changes_table = "".join(changes_rows)
    summary = changes_data["summary"]
    hidden_count = max(0, len(all_changes) - len(visible_changes))

    llm_html = ""
    if llm_explanation:
        try:
            import markdown
            llm_html = markdown.markdown(llm_explanation)
        except ImportError:
            llm_html = html.escape(llm_explanation).replace("\n", "<br>")

    timestamp_escaped = html.escape(changes_data["timestamp"])
    plan_file_escaped = html.escape(str(config.plan_file))

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Terraform Plan Dashboard</title>
<style>
:root {{
    --bg: #0b0e14;
    --surface: #12161f;
    --surface-2: #171c27;
    --surface-3: #1d2330;
    --border: #242b38;
    --text: #e8eaf0;
    --text-dim: #8b93a7;
    --text-faint: #5b6472;
    --blue: #5b9dff;
    --green: #34d399;
    --amber: #fbbf24;
    --red: #f87171;
    --purple: #b794f6;
    --radius: 10px;
    --font-ui: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, sans-serif;
    --font-mono: "SF Mono", "JetBrains Mono", "IBM Plex Mono", Consolas, monospace;
}}
* {{ box-sizing: border-box; }}
body {{
    font-family: var(--font-ui);
    background: var(--bg);
    background-image:
        radial-gradient(circle at 15% 0%, rgba(91,157,255,0.08), transparent 40%),
        radial-gradient(circle at 85% 0%, rgba(183,148,246,0.06), transparent 40%);
    color: var(--text);
    margin: 0;
    padding: 24px;
    line-height: 1.5;
}}
a {{ color: var(--blue); }}
.mono {{ font-family: var(--font-mono); }}
.container {{
    max-width: 1600px;
    margin: auto;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 16px;
    overflow: hidden;
    box-shadow: 0 20px 60px rgba(0,0,0,0.45);
}}

/* Header */
.header {{
    padding: 28px 32px 24px;
    border-bottom: 1px solid var(--border);
    background: linear-gradient(180deg, var(--surface-2), var(--surface));
}}
.header-top {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 16px;
    flex-wrap: wrap;
}}
.header-eyebrow {{
    font-family: var(--font-mono);
    font-size: 11px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--blue);
    margin: 0 0 6px;
}}
.header h1 {{
    margin: 0;
    font-size: 24px;
    font-weight: 650;
    letter-spacing: -0.01em;
}}
.header-meta {{
    font-family: var(--font-mono);
    font-size: 12.5px;
    color: var(--text-dim);
    margin-top: 6px;
}}
.header-meta span {{ color: var(--text); }}

/* Risk strip - signature element */
.risk-strip-wrap {{ margin-top: 20px; }}
.risk-strip-label {{
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--text-faint);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 6px;
}}
.risk-strip {{
    display: flex;
    width: 100%;
    height: 8px;
    border-radius: 4px;
    overflow: hidden;
    background: var(--surface-3);
}}
.risk-seg {{ height: 100%; min-width: 2px; }}
.risk-legend {{
    display: flex;
    flex-wrap: wrap;
    gap: 14px;
    margin-top: 8px;
    font-size: 12px;
    color: var(--text-dim);
}}
.risk-legend-item {{ display: flex; align-items: center; gap: 6px; }}
.risk-legend-item i {{ width: 8px; height: 8px; border-radius: 2px; display: inline-block; }}

/* Stat cards */
.cards {{
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 1px;
    background: var(--border);
    border-bottom: 1px solid var(--border);
}}
.card {{
    background: var(--surface);
    padding: 20px 18px;
}}
.card-label {{
    font-size: 11.5px;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 0.06em;
}}
.card-number {{
    font-family: var(--font-mono);
    font-size: 30px;
    font-weight: 600;
    margin-top: 6px;
}}

/* AI review */
.llm-section {{
    padding: 26px 32px;
    background: rgba(91,157,255,0.06);
    border-bottom: 1px solid var(--border);
}}
.llm-section h2 {{
    font-size: 14px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--blue);
    margin: 0 0 12px;
    font-family: var(--font-mono);
}}
.llm-body {{ color: var(--text); font-size: 14.5px; }}
.llm-body :is(h1,h2,h3) {{ color: var(--text); }}
.llm-body code {{ font-family: var(--font-mono); background: var(--surface-3); padding: 1px 5px; border-radius: 4px; }}

/* Controls */
.controls {{
    padding: 18px 32px;
    background: var(--surface-2);
    border-bottom: 1px solid var(--border);
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    align-items: center;
}}
#searchInput {{
    flex: 1 1 260px;
    padding: 10px 14px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--surface);
    color: var(--text);
    font-size: 13.5px;
    outline: none;
}}
#searchInput:focus {{ border-color: var(--blue); box-shadow: 0 0 0 3px rgba(91,157,255,0.15); }}
.filter-group {{ display: flex; flex-wrap: wrap; gap: 6px; }}
.filter-chip {{
    font-family: var(--font-mono);
    font-size: 11.5px;
    padding: 6px 12px;
    border-radius: 999px;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--text-dim);
    cursor: pointer;
    user-select: none;
    transition: all 0.12s ease;
}}
.filter-chip:hover {{ border-color: var(--blue); color: var(--text); }}
.filter-chip.active {{ background: var(--blue); border-color: var(--blue); color: #0b0e14; font-weight: 600; }}
.results-count {{ font-family: var(--font-mono); font-size: 12px; color: var(--text-faint); }}

/* Table */
.table-wrap {{ overflow: auto; max-height: 78vh; }}
table {{ width: 100%; border-collapse: collapse; }}
thead th {{
    position: sticky;
    top: 0;
    background: var(--surface-2);
    color: var(--text-dim);
    text-align: left;
    padding: 12px 16px;
    font-size: 11.5px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    border-bottom: 1px solid var(--border);
    z-index: 2;
}}
tbody tr {{ border-bottom: 1px solid var(--border); }}
tbody tr:hover {{ background: var(--surface-2); }}
tbody td {{ padding: 14px 16px; vertical-align: top; font-size: 13.5px; }}
.col-action {{ white-space: nowrap; font-weight: 600; font-size: 12.5px; }}
.action-icon {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 20px; height: 20px;
    border-radius: 5px;
    font-weight: 700;
    margin-right: 6px;
    font-size: 12px;
}}
.col-address {{ font-size: 12px; color: var(--text-dim); }}
.chip {{
    display: inline-block;
    margin-top: 8px;
    padding: 3px 9px;
    border-radius: 999px;
    font-size: 10.5px;
    font-weight: 600;
    color: #0b0e14;
}}
.chip-neutral {{ background: var(--surface-3); color: var(--text-dim); font-weight: 500; }}

/* Details / disclosure */
.detail-toggle {{
    cursor: pointer;
    color: var(--blue);
    font-size: 12.5px;
    font-weight: 600;
    list-style: none;
}}
.detail-toggle::-webkit-details-marker {{ display: none; }}
.detail-toggle::before {{ content: "▸ "; }}
details[open] > .detail-toggle::before {{ content: "▾ "; }}
.detail-toggle--sub {{ color: var(--text-dim); }}
.detail-toggle--warn {{ color: var(--red); }}
.detail-block {{ margin-top: 10px; }}
.diff-wrap {{ overflow: auto; margin-top: 10px; border-radius: 8px; border: 1px solid var(--border); }}

.cost-badge {{
    margin-top: 10px;
    padding: 8px 10px;
    border-radius: 8px;
    background: var(--surface-3);
    font-size: 12px;
    display: flex;
    flex-direction: column;
    gap: 2px;
}}
.cost-badge-label {{ color: var(--text-faint); font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.05em; }}
.cost-badge-value {{ font-family: var(--font-mono); font-weight: 700; }}
.cost-badge-total {{ color: var(--text-dim); font-size: 11px; }}
.cost-up .cost-badge-value {{ color: var(--red); }}
.cost-down .cost-badge-value {{ color: var(--green); }}
.cost-flat .cost-badge-value {{ color: var(--blue); }}

.mini-table {{ width: 100%; margin-top: 8px; font-size: 12px; border-collapse: collapse; }}
.mini-table td {{ padding: 5px 6px; border-bottom: 1px solid var(--border); }}

.affected-box {{
    margin-top: 8px;
    padding: 10px;
    background: rgba(248,113,113,0.08);
    border: 1px solid rgba(248,113,113,0.25);
    border-radius: 8px;
    font-size: 11.5px;
}}
.affected-box ul {{ margin: 0; padding-left: 16px; color: var(--text-dim); }}

.empty-state {{
    padding: 60px 20px;
    text-align: center;
    color: var(--text-faint);
    font-family: var(--font-mono);
    font-size: 13px;
}}

.footnote {{
    padding: 14px 32px;
    font-size: 11.5px;
    color: var(--text-faint);
    font-family: var(--font-mono);
    border-top: 1px solid var(--border);
}}

/* difflib output re-themed */
table.diff {{ background: var(--surface); color: var(--text); font-family: var(--font-mono); font-size: 11.5px; width: 100%; border-collapse: collapse; }}
table.diff td, table.diff th {{ padding: 2px 6px; }}
.diff_header {{ background: var(--surface-2); color: var(--text-faint); }}
td.diff_header {{ text-align: right; }}
.diff_next {{ background: var(--surface-2); }}
.diff_add {{ background: rgba(52,211,153,0.18); color: var(--green); }}
.diff_chg {{ background: rgba(251,191,36,0.18); color: var(--amber); }}
.diff_sub {{ background: rgba(248,113,113,0.18); color: var(--red); }}

@media (max-width: 1100px) {{
    .cards {{ grid-template-columns: repeat(3, 1fr); }}
}}
@media (max-width: 900px) {{
    .cards {{ grid-template-columns: repeat(2, 1fr); }}
    body {{ padding: 10px; }}
}}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <div class="header-top">
            <div>
                <p class="header-eyebrow">Terraform Plan Analysis</p>
                <h1>Infrastructure Change Report</h1>
                <div class="header-meta">Plan file: <span>{plan_file_escaped}</span> · Generated: <span>{timestamp_escaped}</span></div>
            </div>
        </div>
        <div class="risk-strip-wrap">
            <div class="risk-strip-label">Risk composition</div>
            <div class="risk-strip">{risk_segments}</div>
            <div class="risk-legend">{risk_legend}</div>
        </div>
    </div>

    <div class="cards">
        <div class="card"><div class="card-label">Total changes</div><div class="card-number">{summary["total"]}</div></div>
        <div class="card"><div class="card-label">Create</div><div class="card-number" style="color:var(--green);">{summary["create"]}</div></div>
        <div class="card"><div class="card-label">Update</div><div class="card-number" style="color:var(--amber);">{summary["update"]}</div></div>
        <div class="card"><div class="card-label">Delete</div><div class="card-number" style="color:var(--red);">{summary["delete"]}</div></div>
        <div class="card"><div class="card-label">High risk</div><div class="card-number" style="color:{'var(--red)' if high_risk_count else 'var(--text-dim)'};">{high_risk_count}</div></div>
        <div class="card"><div class="card-label">Total monthly cost</div><div class="card-number" style="color:var(--blue);">${total_monthly_cost:,.2f}</div></div>
    </div>

    {f'<div class="llm-section"><h2>AI Architecture Review</h2><div class="llm-body">{llm_html}</div></div>' if llm_explanation else ''}

    <div class="controls">
        <input type="text" id="searchInput" placeholder="Search by address, type, or provider…" onkeyup="filterTable()">
        <div class="filter-group" id="actionFilters" data-kind="action">
            <button class="filter-chip active" data-value="all">All actions</button>
            <button class="filter-chip" data-value="create">Create</button>
            <button class="filter-chip" data-value="update">Update</button>
            <button class="filter-chip" data-value="delete">Delete</button>
            <button class="filter-chip" data-value="replace">Replace</button>
        </div>
        <span class="results-count" id="resultsCount"></span>
    </div>

    <div class="table-wrap">
        <table>
            <thead>
                <tr><th>Action</th><th>Address</th><th>Type</th><th>Provider / Risk</th><th>Impact details</th></tr>
            </thead>
            <tbody id="changesBody">{changes_table if changes_table else ''}</tbody>
        </table>
        {f'<div class="empty-state">No changes to display</div>' if not changes_table else ''}
    </div>

    {f'<div class="footnote">Showing {len(visible_changes)} of {len(all_changes)} changes ({hidden_count} not rendered — increase max_table_rows to see more).</div>' if hidden_count else ''}
</div>
<script>
const searchInput = document.getElementById("searchInput");
const rows = () => Array.from(document.querySelectorAll("#changesBody tr"));
const resultsCount = document.getElementById("resultsCount");
let activeAction = "all";

function updateCount() {{
    const visible = rows().filter(r => r.style.display !== "none").length;
    resultsCount.textContent = `${{visible}} / ${{rows().length}} shown`;
}}

function filterTable() {{
    const term = searchInput.value.toLowerCase();
    rows().forEach(row => {{
        const matchesSearch = row.innerText.toLowerCase().includes(term);
        const matchesAction = activeAction === "all" || row.dataset.action === activeAction;
        row.style.display = (matchesSearch && matchesAction) ? "" : "none";
    }});
    updateCount();
}}

document.getElementById("actionFilters").addEventListener("click", (e) => {{
    const btn = e.target.closest(".filter-chip");
    if (!btn) return;
    document.querySelectorAll("#actionFilters .filter-chip").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    activeAction = btn.dataset.value;
    filterTable();
}});

updateCount();
</script>
</body>
</html>"""

    logger.info("✅ HTML report generated successfully")
    return html_content
