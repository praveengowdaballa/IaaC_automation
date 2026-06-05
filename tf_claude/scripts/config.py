"""
scripts/config.py
TerraformDiffConfig dataclass with validation and CLI factory.
"""

import argparse
import ipaddress
import logging
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from scripts.logger import logger


@dataclass
class TerraformDiffConfig:
    """
    Configuration for TerraformDiffGenerator with validation.

    Attributes:
        plan_file: Path to Terraform plan file (binary .tfplan or .json)
        terraform_dir: Path to Terraform working directory
        ollama_url: URL to Ollama LLM service
        llm_model: Ollama model name
        output_file: Output HTML file path
        enable_llm: Whether to enable LLM analysis
        max_table_rows: Maximum rows to display in HTML table
        command_timeout: Timeout for subprocess commands (seconds)
        log_file: Optional path to write logs
    """

    plan_file: Path
    terraform_dir: Path
    ollama_url: str = "http://localhost:11434"
    llm_model: str = "llama3.1"
    output_file: Path = field(default_factory=lambda: Path("terraform-plan-report.html"))
    enable_llm: bool = True
    max_table_rows: int = 200
    command_timeout: int = 300
    log_file: Optional[str] = None

    # Design constants
    COLORS: dict = field(default_factory=lambda: {
        "delete": "#dc3545",
        "create": "#28a745",
        "update": "#ffc107",
        "replace": "#e83e8c",
    })

    RISK_COLORS: dict = field(default_factory=lambda: {
        "critical": "#dc3545",
        "high": "#fd7e14",
        "medium": "#ffc107",
        "low": "#28a745",
    })

    def validate(self) -> bool:
        """
        Validate all configuration parameters.

        Raises:
            FileNotFoundError: If plan or terraform directory doesn't exist
            ValueError: If URLs or parameters are invalid

        Returns:
            True if all validations pass
        """
        logger.debug("Validating configuration...")

        if not self.plan_file.exists():
            raise FileNotFoundError(
                f"Plan file not found: {self.plan_file.absolute()}\n"
                f"Make sure the path is correct and the file exists."
            )

        if not self.plan_file.is_file():
            raise ValueError(f"Plan file is not a regular file: {self.plan_file.absolute()}")

        try:
            self.plan_file.resolve()
        except (OSError, RuntimeError) as e:
            raise ValueError(f"Cannot resolve plan file path: {e}")

        if not self.terraform_dir.exists():
            raise FileNotFoundError(
                f"Terraform directory not found: {self.terraform_dir.absolute()}\n"
                f"Required for binary plan conversion with 'terraform show'"
            )

        if not self.terraform_dir.is_dir():
            raise ValueError(
                f"Terraform path is not a directory: {self.terraform_dir.absolute()}"
            )

        try:
            parsed = urllib.parse.urlparse(self.ollama_url)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError("Missing scheme (http/https) or hostname")

            if parsed.scheme not in ["http", "https"]:
                raise ValueError(f"Invalid scheme: {parsed.scheme}. Must be http or https")

            if parsed.hostname:
                hostname_lower = parsed.hostname.lower()
                if hostname_lower not in ["localhost", "127.0.0.1", "::1"]:
                    try:
                        ip = ipaddress.ip_address(parsed.hostname)
                        if not ip.is_private:
                            logger.warning(
                                f"Ollama URL points to non-private IP: {parsed.hostname}. "
                                f"Ensure this is intentional."
                            )
                    except ValueError:
                        pass
        except ValueError as e:
            raise ValueError(f"Invalid Ollama URL '{self.ollama_url}': {e}")

        if not self.llm_model or not isinstance(self.llm_model, str):
            raise ValueError("LLM model name must be a non-empty string")

        if self.command_timeout < 1:
            raise ValueError(f"Command timeout must be >= 1 second, got {self.command_timeout}")

        if self.max_table_rows < 10:
            raise ValueError(f"Max table rows must be >= 10, got {self.max_table_rows}")

        logger.info("✅ Configuration validated successfully")
        return True

    @classmethod
    def from_cli_args(cls, args: argparse.Namespace) -> "TerraformDiffConfig":
        """Create configuration from CLI arguments."""
        return cls(
            plan_file=Path(args.plan_file),
            terraform_dir=Path(args.terraform_dir),
            ollama_url=args.ollama_url,
            llm_model=args.llm_model,
            output_file=Path(args.output),
            enable_llm=not args.no_llm,
            log_file=args.log_file if hasattr(args, "log_file") else None,
        )
