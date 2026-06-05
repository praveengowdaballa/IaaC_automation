"""
scripts/html_reporter.py
Generates the interactive HTML dashboard from extracted Terraform changes.
"""

import difflib
import html
import json
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
        "create": "➕",
        "update": "✏️",
        "delete": "🗑️",
        "replace": "🔄",
    }

    changes_rows = []

    for change in changes_data["changes"][: config.max_table_rows]:
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

        diff_html = ""
        cost_str = ""
        component_html = ""
        affected_str = ""

        if action in ["update", "replace"] and change["before"] and change["after"]:
            diff_html = f"""
            <details>
                <summary style="cursor:pointer;color:#667eea;font-weight:bold;">View JSON Diff</summary>
                <div style="overflow:auto;margin-top:10px;">{generate_diff_html(change["before"], change["after"])}</div>
            </details>
            """

        if monthly_cost > 0 or diff_cost != 0:
            badge_bg = (
                "#ffebee" if diff_cost > 0 else "#e8f5e9" if diff_cost < 0 else "#e3f2fd"
            )
            text_color = (
                "#c62828" if diff_cost > 0 else "#2e7d32" if diff_cost < 0 else "#1565c0"
            )
            sign = "+" if diff_cost > 0 else ""
            cost_str = f"""
            <div style="margin-top:10px;background:{badge_bg};padding:8px;border-radius:6px;font-size:12px;">
                <div style="font-weight:bold;color:{text_color};">💰 Cost Impact: {sign}${diff_cost:.2f}/mo (Total: ${monthly_cost:.2f})</div>
            </div>
            """

        if components:
            component_rows = "".join(
                f"""
                <tr>
                    <td style="padding:4px;">{html.escape(c.get("name", "Unknown"))}</td>
                    <td style="padding:4px;font-weight:bold;">${c.get("monthlyCost", "0")}</td>
                </tr>
                """
                for c in components
            )
            component_html = f"""
            <details style="margin-top:8px;">
                <summary style="cursor:pointer;color:#444;font-size:12px;">📊 Cost Breakdown</summary>
                <table style="width:100%;margin-top:8px;font-size:12px;background:#fafafa;">
                    {component_rows}
                </table>
            </details>
            """

        if change.get("affected_resources"):
            affected_list = "".join(
                f"<li>{html.escape(r)}</li>" for r in change["affected_resources"][:5]
            )
            affected_str = f"""
            <details style="margin-top:10px;">
                <summary style="cursor:pointer;color:#ea6666;font-size:12px;">⚠️ {len(change['affected_resources'])} Dependent Resources</summary>
                <div style="margin-top:8px;padding:8px;background:#fff5f5;border-radius:4px;font-size:11px;">
                    <ul style="margin-left:15px;">{affected_list}</ul>
                </div>
            </details>
            """

        changes_rows.append(f"""
        <tr>
            <td style="padding:12px;color:{color};font-weight:bold;">{icon} {action.upper()}</td>
            <td style="padding:12px;font-family:monospace;font-size:12px;">{address_escaped}</td>
            <td style="padding:12px;">{type_escaped}<br><br>
                <span style="background:#6c757d;color:white;padding:3px 8px;border-radius:10px;font-size:10px;">{category_escaped}</span>
            </td>
            <td style="padding:12px;">{provider_escaped}<br><br>
                <span style="background:{risk_colors.get(change['risk'], '#6c757d')};color:white;padding:4px 8px;border-radius:12px;font-size:11px;font-weight:bold;">{risk_escaped}</span>
            </td>
            <td style="padding:12px;">{diff_html}{cost_str}{component_html}{affected_str}</td>
        </tr>
        """)

    changes_table = "".join(changes_rows)
    summary = changes_data["summary"]

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
<html>
<head>
<meta charset="UTF-8">
<title>Terraform Plan Dashboard</title>
<style>
body {{ font-family:Arial,sans-serif; background:#f4f7f6; padding:20px; }}
.container {{ max-width:1600px; margin:auto; background:white; border-radius:12px; box-shadow:0 10px 30px rgba(0,0,0,0.1); overflow:hidden; }}
.header {{ background:#2c3e50; color:white; padding:30px; }}
.cards {{ display:flex; gap:20px; padding:20px; background:#ecf0f1; flex-wrap:wrap; }}
.card {{ flex:1; min-width:150px; background:white; padding:20px; border-radius:8px; text-align:center; box-shadow:0 2px 5px rgba(0,0,0,0.05); }}
.number {{ font-size:28px; font-weight:bold; }}
.llm-section {{ padding:30px; background:#e8f4f8; border-left:6px solid #3498db; }}
.llm-section h2 {{ color:#2980b9; margin-top:0; }}
table {{ width:100%; border-collapse:collapse; }}
th {{ background:#34495e; color:white; padding:15px; text-align:left; }}
tr {{ border-bottom:1px solid #eee; }}
tr:hover {{ background:#f9f9f9; }}
.search-box {{ padding:20px; background:#f8f9fa; }}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>🏗️ Terraform Architecture & Plan Analysis</h1>
        <p>File: {plan_file_escaped} | Generated: {timestamp_escaped}</p>
    </div>
    <div class="cards">
        <div class="card"><div class="number">{summary["total"]}</div><div>Total Changes</div></div>
        <div class="card"><div class="number" style="color:#28a745;">{summary["create"]}</div><div>Creates/Replaces</div></div>
        <div class="card"><div class="number" style="color:#ffc107;">{summary["update"]}</div><div>Updates</div></div>
        <div class="card"><div class="number" style="color:#dc3545;">{summary["delete"]}</div><div>Deletes</div></div>
        <div class="card"><div class="number" style="color:#8e44ad;">${changes_data['costs']['overall_diff']:.2f}</div><div>Monthly Delta</div></div>
    </div>

    {f'<div class="llm-section"><h2>🤖 AI Architecture Review</h2><div>{llm_html}</div></div>' if llm_explanation else ''}

    <div class="search-box">
        <input type="text" id="searchInput" placeholder="Search resources..."
               style="width:100%;padding:12px;border:1px solid #ccc;border-radius:4px;"
               onkeyup="filterTable()">
    </div>

    <div style="overflow:auto; padding:20px;">
        <table>
            <thead>
                <tr><th>Action</th><th>Address</th><th>Type</th><th>Provider / Risk</th><th>Impact Details</th></tr>
            </thead>
            <tbody>{changes_table}</tbody>
        </table>
    </div>
</div>
<script>
function filterTable() {{
    const filter = document.getElementById("searchInput").value.toLowerCase();
    document.querySelectorAll("tbody tr").forEach(row => {{
        row.style.display = row.innerText.toLowerCase().includes(filter) ? "" : "none";
    }});
}}
</script>
</body>
</html>"""

    logger.info("✅ HTML report generated successfully")
    return html_content
