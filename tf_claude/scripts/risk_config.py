"""
scripts/risk_config.py
Risk classification constants: action rules and high-risk keyword list.

To add new risk rules or keywords, edit this file only — no other module needs changes.
"""

from typing import Dict, List

# Maps a Terraform action to a default risk level
RISK_RULES: Dict[str, str] = {
    "delete": "critical",
    "create": "medium",
    "update": "low",
}

# Resource type substrings that escalate risk
HIGH_RISK_KEYWORDS: List[str] = [
    "iam",
    "security",
    "firewall",
    "network",
    "database",
    "db",
    "kubernetes",
    "cluster",
    "load_balancer",
    "gateway",
    "policy",
    "role",
    "vpn",
    "proxy",
    "vpc",
]
