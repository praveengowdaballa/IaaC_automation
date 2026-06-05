"""
scripts/plan_loader.py
Loads and parses Terraform plan files (JSON or binary .tfplan).
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.config import TerraformDiffConfig
from scripts.logger import logger


def run_command(
    cmd: List[str],
    config: TerraformDiffConfig,
    timeout: Optional[int] = None,
    description: str = "",
) -> Optional[str]:
    """
    Safely execute a subprocess command with timeout and error handling.

    Args:
        cmd: Command to execute as list
        config: Active TerraformDiffConfig (provides default timeout)
        timeout: Timeout in seconds (uses config.command_timeout if None)
        description: Human-readable description of the command

    Returns:
        Command stdout output or None if failed
    """
    timeout = timeout or config.command_timeout
    description = description or " ".join(cmd)

    try:
        logger.debug(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

        if result.returncode != 0:
            logger.error(
                f"{description} failed with exit code {result.returncode}\n"
                f"STDERR: {result.stderr[:500]}"
            )
            return None

        logger.debug(f"{description} completed successfully")
        return result.stdout

    except subprocess.TimeoutExpired:
        logger.error(f"{description} timed out after {timeout} seconds")
        return None
    except FileNotFoundError:
        logger.error(f"Command not found: {cmd[0]}. Please ensure it's in PATH.")
        return None
    except Exception as e:
        logger.error(f"Error running command '{description}': {e}")
        return None


def load_and_parse_plan(
    config: TerraformDiffConfig,
) -> tuple[Dict[str, Any], Optional[Path]]:
    """
    Load and parse Terraform plan file (JSON or binary).

    Args:
        config: Active TerraformDiffConfig

    Returns:
        Tuple of (parsed plan dict, path to JSON plan used for Infracost)

    Raises:
        FileNotFoundError: If plan file not found
        json.JSONDecodeError: If plan JSON is invalid
        RuntimeError: If binary plan conversion fails
    """
    logger.info(f"Loading Terraform plan from: {config.plan_file}")
    json_plan_path: Optional[Path] = None

    # Try JSON first
    try:
        with open(config.plan_file, "r", encoding="utf-8") as f:
            tf_json = json.load(f)

        if "resource_changes" in tf_json:
            logger.info("✅ Plan loaded as JSON directly")
            json_plan_path = config.plan_file
            return tf_json, json_plan_path
    except json.JSONDecodeError as e:
        logger.debug(f"Not a valid JSON file (line {e.lineno}): {e.msg}")
    except UnicodeDecodeError:
        logger.debug("File is not UTF-8 encoded, likely a binary plan")
    except Exception as e:
        logger.error(f"Error reading plan file: {e}")
        raise

    # Binary plan — convert with terraform show
    logger.info("Converting binary plan to JSON using 'terraform show'...")
    original_dir = os.getcwd()

    try:
        os.chdir(config.terraform_dir)

        stdout = run_command(
            ["terraform", "show", "-json", str(config.plan_file.absolute())],
            config=config,
            timeout=config.command_timeout,
            description="terraform show",
        )

        if not stdout:
            raise RuntimeError("Failed to convert binary plan using 'terraform show'")

        try:
            tf_json = json.loads(stdout)
        except json.JSONDecodeError as e:
            raise json.JSONDecodeError(
                f"terraform show output is not valid JSON: {e.msg}", e.doc, e.pos
            )

        with tempfile.NamedTemporaryFile(
            suffix=".json", delete=False, mode="w", encoding="utf-8"
        ) as tmp:
            json.dump(tf_json, tmp)
            json_plan_path = Path(tmp.name)
            logger.debug(f"Saved temporary JSON plan to: {json_plan_path}")

        return tf_json, json_plan_path

    except Exception as e:
        logger.error(f"Failed to parse plan file: {e}")
        raise
    finally:
        os.chdir(original_dir)
