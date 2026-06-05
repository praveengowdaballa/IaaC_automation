"""
scripts/cost_analyzer.py
Retrieves and parses Infracost data for Terraform plan resources.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from scripts.config import TerraformDiffConfig
from scripts.logger import logger
from scripts.plan_loader import run_command


def get_infracost_data(
    config: TerraformDiffConfig,
    json_plan_path: Optional[Path],
) -> Dict[str, Any]:
    """
    Get cost impact data from Infracost.

    Args:
        config: Active TerraformDiffConfig
        json_plan_path: Path to the JSON plan file (may be a temp file)

    Returns:
        Dictionary with cost data or empty dict if Infracost unavailable
    """
    logger.info("Calculating cloud cost impact using Infracost...")

    version_output = run_command(
        ["infracost", "--version"],
        config=config,
        timeout=10,
        description="infracost --version",
    )

    if not version_output:
        logger.warning("Infracost CLI not available. Skipping cost analysis.")
        return {}

    logger.debug(f"Infracost version: {version_output.strip()}")

    if not os.getenv("INFRACOST_API_KEY"):
        logger.warning(
            "INFRACOST_API_KEY environment variable not set. "
            "Cost details may be incomplete. See https://www.infracost.io/docs"
        )

    if not json_plan_path:
        logger.warning("No JSON plan available for Infracost analysis")
        return {}

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp_json:
        infracost_json_path = tmp_json.name

    try:
        cmd = [
            "infracost",
            "breakdown",
            "--path",
            str(json_plan_path),
            "--format",
            "json",
            "--out-file",
            infracost_json_path,
        ]

        output = run_command(cmd, config=config, description="infracost breakdown")

        if output is None:
            logger.warning("Infracost command failed")
            return {}

        if not Path(infracost_json_path).exists():
            logger.warning("Infracost output JSON not created")
            return {}

        if Path(infracost_json_path).stat().st_size == 0:
            logger.warning("Infracost output JSON is empty")
            return {}

        with open(infracost_json_path, "r", encoding="utf-8") as f:
            cost_data = json.load(f)

        resource_costs: Dict[str, Dict[str, float]] = {}
        projects = cost_data.get("projects", [])

        for project in projects:
            breakdown_resources = project.get("breakdown", {}).get("resources", [])
            past_breakdown = project.get("pastBreakdown", {})
            past_resources = past_breakdown.get("resources", []) if past_breakdown else []

            past_lookup = {
                r.get("name", ""): r for r in past_resources if r.get("name")
            }

            for res in breakdown_resources:
                resource_name = res.get("name", "")
                if not resource_name:
                    continue

                monthly_cost = float(res.get("monthlyCost", 0) or 0)
                if not monthly_cost:
                    monthly_cost = sum(
                        float(c.get("monthlyCost", 0) or 0)
                        for c in res.get("costComponents", [])
                    )

                past_cost = 0.0
                if resource_name in past_lookup:
                    past_res = past_lookup[resource_name]
                    past_cost = float(past_res.get("monthlyCost", 0) or 0)
                    if not past_cost:
                        past_cost = sum(
                            float(c.get("monthlyCost", 0) or 0)
                            for c in past_res.get("costComponents", [])
                        )

                diff_cost = monthly_cost - past_cost

                if monthly_cost > 0 or past_cost > 0 or diff_cost != 0:
                    resource_costs[resource_name] = {
                        "monthly_cost": monthly_cost,
                        "past_cost": past_cost,
                        "diff_cost": diff_cost,
                        "components": res.get("costComponents", []),
                    }

        logger.info(f"✅ Infracost analysis complete: {len(resource_costs)} resources")

        return {
            "overall_diff": float(cost_data.get("diffTotalMonthlyCost", 0.0)),
            "overall_past": float(cost_data.get("pastTotalMonthlyCost", 0.0)),
            "overall_current": float(cost_data.get("totalMonthlyCost", 0.0)),
            "currency": cost_data.get("currency", "USD"),
            "resources": resource_costs,
        }

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON from Infracost (line {e.lineno}): {e.msg}")
        return {}
    except Exception as e:
        logger.error(f"Error processing Infracost data: {e}")
        return {}
    finally:
        try:
            Path(infracost_json_path).unlink(missing_ok=True)
        except Exception as e:
            logger.debug(f"Could not delete temporary infracost file: {e}")
