"""
scripts/llm_analyzer.py
Sends Terraform change summaries to a local Ollama LLM for architecture review.
"""

from typing import Any, Dict

from scripts.config import TerraformDiffConfig
from scripts.logger import logger

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


def get_llm_explanation(
    config: TerraformDiffConfig,
    changes_data: Dict[str, Any],
) -> str:
    """
    Get LLM-based architecture review of changes.

    Args:
        config: Active TerraformDiffConfig
        changes_data: Dictionary with extracted changes (from change_extractor)

    Returns:
        LLM explanation string or error message
    """
    if not HAS_REQUESTS:
        logger.warning("requests library not installed, skipping LLM analysis")
        return "LLM explanation unavailable (requests library not installed)"

    resource_details = []
    for c in changes_data["changes"]:
        if c["action"] != "read":
            resource_details.append(
                f"[{c['action'].upper()}] {c['address']} "
                f"(Type: {c['type']}, Risk: {c['risk']})"
            )

    details_str = "\n".join(resource_details[:40])
    if len(resource_details) > 40:
        details_str += (
            f"\n... and {len(resource_details) - 40} additional changes omitted for brevity."
        )

    prompt = f"""You are a Lead DevOps Architect performing a strict, technical review of a Terraform plan.
Your task is to analyze the EXACT resources being modified below.

DO NOT provide generic advice like "check IAM policies" or "implement logging" UNLESS an IAM policy
or logging resource is explicitly listed below. Base your analysis 100% on the specific resources listed.

SPECIFIC RESOURCES CHANGING:
{details_str}

Provide your analysis in the following strict format. Keep answers concise and technical:

### 🔒 Security & Blast Radius
(Analyze specific vulnerabilities related to the resource types listed above.)

### 📐 Architecture & Best Practices
(Identify any potential anti-patterns or optimization opportunities based strictly on the resources.)

### ⚠️ Execution Risks
(Identify dependencies or state issues that could cause this terraform apply to fail.)
"""

    try:
        logger.debug(f"Sending LLM request to {config.ollama_url}")
        response = requests.post(
            f"{config.ollama_url}/api/generate",
            json={
                "model": config.llm_model,
                "prompt": prompt,
                "stream": False,
                "temperature": 0.1,
            },
            timeout=config.command_timeout,
        )

        if response.status_code == 200:
            result = response.json().get("response", "No analysis generated")
            logger.info("✅ LLM analysis completed")
            return result

        error_msg = f"LLM analysis failed (HTTP {response.status_code})"
        logger.error(f"{error_msg}: {response.text[:200]}")
        return error_msg

    except requests.exceptions.Timeout:
        error_msg = f"LLM request timed out after {config.command_timeout}s"
        logger.error(error_msg)
        return error_msg
    except requests.exceptions.ConnectionError as e:
        error_msg = f"Could not connect to Ollama at {config.ollama_url}"
        logger.error(f"{error_msg}: {e}")
        return error_msg
    except requests.exceptions.RequestException as e:
        logger.error(f"LLM request failed: {e}")
        return f"LLM analysis unavailable: {str(e)}"
    except Exception as e:
        logger.error(f"Unexpected error during LLM analysis: {e}")
        return f"LLM analysis failed: {str(e)}"
