"""
scripts/change_extractor.py
Extracts, risk-scores, and categorises resource changes from a Terraform plan.
"""

from datetime import datetime
from typing import Any, Dict, List

from scripts.config import TerraformDiffConfig
from scripts.cost_analyzer import get_infracost_data
from scripts.logger import logger
from scripts.plan_loader import load_and_parse_plan
from scripts.resource_mapper import TerraformResourceMapper
from scripts.risk_config import HIGH_RISK_KEYWORDS, RISK_RULES


def calculate_risk(resource_type: str, action: str) -> str:
    """
    Calculate risk level for a resource change.

    Args:
        resource_type: Terraform resource type
        action: Change action (create, update, delete, replace)

    Returns:
        Risk level string: critical | high | medium | low
    """
    base_risk = RISK_RULES.get(action, "low")
    resource_lower = resource_type.lower()

    for keyword in HIGH_RISK_KEYWORDS:
        if keyword in resource_lower:
            if action == "delete":
                return "critical"
            elif action == "update":
                return "high"
            else:
                return "medium"

    return base_risk


def categorize_resource(resource_type: str) -> str:
    """
    Categorize resource by type.

    Args:
        resource_type: Terraform resource type

    Returns:
        Category: security | network | compute | database | container | storage | general
    """
    categories = {
        "security": ["iam", "policy", "security", "firewall", "role"],
        "network": ["network", "subnet", "vpc", "gateway", "route", "proxy"],
        "compute": ["instance", "vm", "compute", "server"],
        "database": ["db", "database", "sql"],
        "container": ["kubernetes", "cluster", "container"],
        "storage": ["bucket", "storage", "disk"],
    }

    resource_lower = resource_type.lower()
    for category, keywords in categories.items():
        if any(k in resource_lower for k in keywords):
            return category

    return "general"


def extract_changes(
    config: TerraformDiffConfig,
    resource_mapper: TerraformResourceMapper,
) -> Dict[str, Any]:
    """
    Extract and analyse changes from a Terraform plan.

    Args:
        config: Active TerraformDiffConfig
        resource_mapper: Initialised TerraformResourceMapper (will be populated)

    Returns:
        Dictionary with keys: timestamp, summary, changes, costs
    """
    logger.info("Extracting changes from Terraform plan...")

    tf_json, json_plan_path = load_and_parse_plan(config)
    resource_mapper.parse_resource_references(tf_json)
    cost_impact = get_infracost_data(config, json_plan_path)

    changes: List[Dict[str, Any]] = []

    for resource in tf_json.get("resource_changes", []):
        try:
            actions = resource.get("change", {}).get("actions", [])
            if not actions or actions[0] == "no-op":
                continue

            action = actions[0]

            if len(actions) > 1 and "create" in actions and "delete" in actions:
                action = "replace"

            resource_type = resource.get("type", "unknown")
            address = resource.get("address", "unknown")

            # Match Infracost data to this resource
            res_cost = cost_impact.get("resources", {}).get(address, {})
            if not res_cost:
                for key in cost_impact.get("resources", {}):
                    if address in key or key in address:
                        res_cost = cost_impact["resources"][key]
                        break

            changes.append({
                "address": address,
                "type": resource_type,
                "action": action,
                "provider": resource.get("provider_name", "unknown"),
                "before": resource.get("change", {}).get("before"),
                "after": resource.get("change", {}).get("after"),
                "risk": calculate_risk(resource_type, action),
                "category": categorize_resource(resource_type),
                "affected_resources": list(
                    resource_mapper.find_affected_resources(address)
                ),
                "costs": {
                    "monthly_cost": res_cost.get("monthly_cost", 0.0),
                    "past_cost": res_cost.get("past_cost", 0.0),
                    "diff_cost": res_cost.get("diff_cost", 0.0),
                    "currency": cost_impact.get("currency", "USD"),
                    "components": res_cost.get("components", []),
                },
            })

        except (KeyError, TypeError, AttributeError) as e:
            logger.warning(
                f"Error processing resource {resource.get('address', 'unknown')}: {e}"
            )
            continue

    summary = {
        "total": len(changes),
        "create": sum(1 for c in changes if c["action"] in ["create", "replace"]),
        "update": sum(1 for c in changes if c["action"] == "update"),
        "delete": sum(1 for c in changes if c["action"] in ["delete", "replace"]),
        "providers": list(set(c["provider"] for c in changes)),
    }

    logger.info(
        f"✅ Extracted {summary['total']} changes: "
        f"{summary['create']} creates, {summary['update']} updates, "
        f"{summary['delete']} deletes"
    )

    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": summary,
        "changes": changes,
        "costs": {
            "overall_diff": cost_impact.get("overall_diff", 0.0),
            "overall_past": cost_impact.get("overall_past", 0.0),
            "overall_current": cost_impact.get("overall_current", 0.0),
            "currency": cost_impact.get("currency", "USD"),
        },
        # Expose json_plan_path so the generator can clean it up
        "_json_plan_path": json_plan_path,
    }
