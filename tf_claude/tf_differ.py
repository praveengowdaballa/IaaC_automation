#!/usr/bin/env python3
"""
tf_differ.py  —  Terraform Plan Diff HTML Dashboard
Cloud Agnostic | Risk Aware | Interactive Dashboard | FinOps Cost Tracking

This is the main entry point. All logic lives in scripts/:
  scripts/logger.py          — logging setup
  scripts/config.py          — TerraformDiffConfig dataclass + CLI factory
  scripts/risk_config.py     — RISK_RULES and HIGH_RISK_KEYWORDS constants
  scripts/resource_mapper.py — TerraformResourceMapper (dependency graph)
  scripts/plan_loader.py     — load_and_parse_plan + run_command
  scripts/cost_analyzer.py   — get_infracost_data
  scripts/change_extractor.py— extract_changes, calculate_risk, categorize_resource
  scripts/llm_analyzer.py    — get_llm_explanation (Ollama)
  scripts/html_reporter.py   — generate_html_report, generate_diff_html

Adding a new feature
--------------------
1. Create scripts/my_feature.py with your function(s).
2. Import and call it here (or wire it into an existing step).
3. No changes to __init__.py needed — it auto-discovers everything.

Usage:
    python3 tf_differ.py --plan-file infra.tfplan --terraform-dir .
    python3 tf_differ.py --plan-file plan.json --output dashboard.html --no-llm
    python3 tf_differ.py --plan-file plan.tfplan --log-file analyze.log --verbose
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# scripts/__init__.py auto-imports all modules in the package
from scripts.change_extractor import extract_changes
from scripts.config import TerraformDiffConfig
from scripts.html_reporter import generate_html_report
from scripts.llm_analyzer import HAS_REQUESTS, get_llm_explanation
from scripts.logger import logger, setup_logger
from scripts.resource_mapper import TerraformResourceMapper


# ============================================================================
# GENERATOR  (thin orchestrator — no logic lives here)
# ============================================================================

class TerraformDiffGenerator:
    """Orchestrates the full analysis pipeline."""

    def __init__(self, config: TerraformDiffConfig) -> None:
        self.config = config
        self.resource_mapper = TerraformResourceMapper()
        self._json_plan_path = None  # set after extract_changes
        logger.debug(f"Initialised TerraformDiffGenerator with plan: {config.plan_file}")

    def run(self) -> bool:
        """
        Execute the full Terraform diff analysis and report generation.

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info("=" * 70)
            logger.info("Starting Terraform Plan Analysis")
            logger.info("=" * 70)

            # ── Step 1: Extract changes ──────────────────────────────────────
            changes = extract_changes(self.config, self.resource_mapper)
            self._json_plan_path = changes.pop("_json_plan_path", None)

            # ── Step 2: LLM review (optional) ────────────────────────────────
            llm_explanation = ""
            if self.config.enable_llm and HAS_REQUESTS:
                logger.info("🤖 Generating LLM architecture review...")
                llm_explanation = get_llm_explanation(self.config, changes)

            # ── Step 3: HTML report ───────────────────────────────────────────
            logger.info("📄 Generating HTML report...")
            html_content = generate_html_report(self.config, changes, llm_explanation)

            # ── Step 4: Write output ──────────────────────────────────────────
            self.config.output_file.write_text(html_content, encoding="utf-8")
            logger.info(f"✅ Report generated: {self.config.output_file.absolute()}")

            return True

        except FileNotFoundError as e:
            logger.error(f"File not found: {e}")
            return False
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {e}")
            return False
        except Exception as e:
            logger.exception(f"Unexpected error during execution: {e}")
            return False
        finally:
            self._cleanup()

    def _cleanup(self) -> None:
        """Remove temporary files created during execution."""
        if self._json_plan_path and self._json_plan_path != self.config.plan_file:
            try:
                self._json_plan_path.unlink(missing_ok=True)
                logger.debug(f"Cleaned up temporary file: {self._json_plan_path}")
            except OSError as e:
                logger.warning(f"Could not clean up temp JSON plan: {e}")


# ============================================================================
# CLI
# ============================================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Terraform Plan HTML Dashboard with Cost Analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 tf_differ.py --plan-file infra.tfplan --terraform-dir .
  python3 tf_differ.py --plan-file plan.json --output report.html --no-llm
  python3 tf_differ.py --plan-file plan.tfplan --log-file analyze.log --verbose
        """,
    )
    parser.add_argument(
        "--plan-file", default="plan.json",
        help="Path to terraform plan file (binary .tfplan or .json)",
    )
    parser.add_argument(
        "--terraform-dir", default=".",
        help="Terraform working directory (required for binary .tfplan)",
    )
    parser.add_argument(
        "--output", default="terraform-plan-report.html",
        help="Output HTML file name",
    )
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM analysis")
    parser.add_argument("--llm-model", default="llama3.1", help="Ollama model name")
    parser.add_argument(
        "--ollama-url", default="http://localhost:11434", help="Ollama service URL"
    )
    parser.add_argument("--log-file", default=None, help="Optional log file path")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    setup_logger(
        level=logging.DEBUG if args.verbose else logging.INFO,
        log_file=args.log_file,
    )

    logger.info("Terraform Plan Analyzer")
    logger.info(f"Python {sys.version}")

    try:
        config = TerraformDiffConfig.from_cli_args(args)
        config.validate()

        generator = TerraformDiffGenerator(config)
        success = generator.run()

        if success:
            logger.info("=" * 70)
            logger.info("✅ Analysis completed successfully")
            logger.info("=" * 70)
            return 0
        else:
            logger.error("=" * 70)
            logger.error("❌ Analysis failed")
            logger.error("=" * 70)
            return 1

    except (FileNotFoundError, ValueError, RuntimeError) as e:
        logger.error(f"Configuration error: {e}")
        return 1
    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
        return 1
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
