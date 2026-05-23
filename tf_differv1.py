#!/usr/bin/env python3
"""
Enhanced Terraform Plan Diff HTML Generator (Production Ready)
Cloud Agnostic | Risk Aware | Interactive Dashboard | FinOps Cost Tracking

Phase 1 & 2 Improvements:
- Input validation for all paths and URLs
- Module-level logging with file support
- Complete type hints
- Safe subprocess execution with timeouts
- HTML injection protection
- Configuration management
- Comprehensive error handling
- Configuration class

Usage:
    python3 gemini_tf_differ_refactored.py --plan-file infra.tfplan --terraform-dir .
    python3 gemini_tf_differ_refactored.py --plan-file plan.json --output dashboard.html --no-llm
"""

import json
import subprocess
import tempfile
import os
import sys
import logging
import html
import difflib
import urllib.parse
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from collections import Counter, defaultdict
from typing import Dict, List, Set, Optional, Tuple, Any
import argparse

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# ============================================================================
# MODULE-LEVEL LOGGING CONFIGURATION
# ============================================================================

logger = logging.getLogger(__name__)
_logging_configured = False


def setup_logger(
    level: int = logging.INFO,
    log_file: Optional[str] = None,
    force_reconfigure: bool = False
) -> None:
    """
    Configure module-level logging with console and optional file handlers.
    
    Args:
        level: Logging level (INFO, DEBUG, ERROR, WARNING)
        log_file: Optional path to write logs to file
        force_reconfigure: Force reconfiguration even if already configured
    """
    global _logging_configured
    
    if _logging_configured and not force_reconfigure:
        return
    
    # Clear existing handlers to avoid duplicates
    logger.handlers = []
    
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler (optional)
    if log_file:
        try:
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            logger.info(f"Logging to file: {log_file}")
        except IOError as e:
            logger.warning(f"Could not create log file {log_file}: {e}")
    
    logger.setLevel(level)
    _logging_configured = True


# ============================================================================
# CONFIGURATION CLASS (PHASE 2)
# ============================================================================

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
    output_file: Path = Path("terraform-plan-report.html")
    enable_llm: bool = True
    max_table_rows: int = 200
    command_timeout: int = 300
    log_file: Optional[str] = None
    
    # Design constants
    COLORS = {
        'delete': '#dc3545',
        'create': '#28a745',
        'update': '#ffc107',
        'replace': '#e83e8c'
    }
    
    RISK_COLORS = {
        'critical': '#dc3545',
        'high': '#fd7e14',
        'medium': '#ffc107',
        'low': '#28a745'
    }
    
    def validate(self) -> bool:
        """
        Validate all configuration parameters.
        
        Raises:
            FileNotFoundError: If plan or terraform directory doesn't exist
            ValueError: If URLs or parameters are invalid
            
        Returns:
            bool: True if all validations pass
        """
        logger.debug("Validating configuration...")
        
        # Validate plan file
        if not self.plan_file.exists():
            raise FileNotFoundError(
                f"Plan file not found: {self.plan_file.absolute()}\n"
                f"Make sure the path is correct and the file exists."
            )
        
        if not self.plan_file.is_file():
            raise ValueError(
                f"Plan file is not a regular file: {self.plan_file.absolute()}"
            )
        
        try:
            self.plan_file.resolve()  # Verify it's a valid path
        except (OSError, RuntimeError) as e:
            raise ValueError(f"Cannot resolve plan file path: {e}")
        
        # Validate terraform directory
        if not self.terraform_dir.exists():
            raise FileNotFoundError(
                f"Terraform directory not found: {self.terraform_dir.absolute()}\n"
                f"Required for binary plan conversion with 'terraform show'"
            )
        
        if not self.terraform_dir.is_dir():
            raise ValueError(
                f"Terraform path is not a directory: {self.terraform_dir.absolute()}"
            )
        
        # Validate Ollama URL
        try:
            parsed = urllib.parse.urlparse(self.ollama_url)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError("Missing scheme (http/https) or hostname")
            
            if parsed.scheme not in ['http', 'https']:
                raise ValueError(f"Invalid scheme: {parsed.scheme}. Must be http or https")
            
            # Optional: Prevent SSRF attacks by restricting to localhost/private IPs
            if parsed.hostname:
                hostname_lower = parsed.hostname.lower()
                # Allow localhost and private networks for development
                if hostname_lower not in ['localhost', '127.0.0.1', '::1']:
                    try:
                        import ipaddress
                        ip = ipaddress.ip_address(parsed.hostname)
                        if not ip.is_private:
                            logger.warning(
                                f"Ollama URL points to non-private IP: {parsed.hostname}. "
                                f"Ensure this is intentional."
                            )
                    except ValueError:
                        # It's a hostname, not an IP - that's fine for production
                        pass
        except ValueError as e:
            raise ValueError(f"Invalid Ollama URL '{self.ollama_url}': {e}")
        
        # Validate LLM model name
        if not self.llm_model or not isinstance(self.llm_model, str):
            raise ValueError("LLM model name must be a non-empty string")
        
        # Validate timeouts
        if self.command_timeout < 1:
            raise ValueError(f"Command timeout must be >= 1 second, got {self.command_timeout}")
        
        if self.max_table_rows < 10:
            raise ValueError(f"Max table rows must be >= 10, got {self.max_table_rows}")
        
        logger.info("✅ Configuration validated successfully")
        return True
    
    @classmethod
    def from_cli_args(cls, args: argparse.Namespace) -> 'TerraformDiffConfig':
        """Create configuration from CLI arguments."""
        return cls(
            plan_file=Path(args.plan_file),
            terraform_dir=Path(args.terraform_dir),
            ollama_url=args.ollama_url,
            llm_model=args.llm_model,
            output_file=Path(args.output),
            enable_llm=not args.no_llm,
            log_file=args.log_file if hasattr(args, 'log_file') else None
        )


# ============================================================================
# RISK CONFIGURATION
# ============================================================================

RISK_RULES = {
    "delete": "critical",
    "create": "medium",
    "update": "low"
}

HIGH_RISK_KEYWORDS = [
    "iam", "security", "firewall", "network", "database", "db",
    "kubernetes", "cluster", "load_balancer", "gateway", "policy",
    "role", "vpn", "proxy", "vpc"
]


# ============================================================================
# TERRAFORM DEPENDENCY MAPPER
# ============================================================================

class TerraformResourceMapper:
    """Maps Terraform resource dependencies and relationships."""
    
    def __init__(self) -> None:
        """Initialize the resource mapper."""
        self.resources: Dict[str, Dict[str, Any]] = {}
        self.dependencies: Dict[str, Set[str]] = defaultdict(set)
        self.dependents: Dict[str, Set[str]] = defaultdict(set)
    
    def parse_resource_references(self, tf_json: Dict[str, Any]) -> None:
        """
        Parse resource references and dependencies from Terraform JSON.
        
        Args:
            tf_json: Parsed Terraform plan JSON
        """
        try:
            for resource in tf_json.get("resource_changes", []):
                address = resource.get("address", "")
                if address:
                    self.resources[address] = resource
            
            if "configuration" in tf_json:
                self._extract_config_dependencies(tf_json["configuration"])
            
            logger.debug(f"Parsed {len(self.resources)} resources and their dependencies")
        except (KeyError, TypeError) as e:
            logger.warning(f"Error parsing resource references: {e}. Continuing without full dependency mapping.")
    
    def _extract_config_dependencies(self, config: Any) -> None:
        """
        Recursively extract dependencies from Terraform configuration.
        
        Args:
            config: Terraform configuration dict or value
        """
        if not isinstance(config, dict):
            return
        
        for key, value in config.items():
            if key == "resources" and isinstance(value, list):
                for res in value:
                    if not isinstance(res, dict):
                        continue
                    address = res.get("address")
                    depends_on = res.get("depends_on", [])
                    if address and depends_on:
                        for dep in depends_on:
                            if isinstance(dep, str):
                                self.dependencies[address].add(dep)
                                self.dependents[dep].add(address)
            elif isinstance(value, dict):
                self._extract_config_dependencies(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        self._extract_config_dependencies(item)
    
    def find_affected_resources(self, changed_resource: str) -> Set[str]:
        """
        Find all resources affected by a change to the given resource.
        
        Args:
            changed_resource: Resource address that changed
            
        Returns:
            Set of affected resource addresses
        """
        def find_dependents(resource: str) -> Set[str]:
            result = {resource}
            for dependent in self.dependents.get(resource, set()):
                result.update(find_dependents(dependent))
            return result
        
        affected = find_dependents(changed_resource)
        affected.discard(changed_resource)
        return affected


# ============================================================================
# MAIN TERRAFORM DIFF GENERATOR
# ============================================================================

class TerraformDiffGenerator:
    """Main Terraform plan diff generator with cost tracking and LLM analysis."""
    
    def __init__(self, config: TerraformDiffConfig) -> None:
        """
        Initialize the Terraform diff generator.
        
        Args:
            config: Configuration object
        """
        self.config = config
        self.resource_mapper = TerraformResourceMapper()
        self.json_plan_path: Optional[Path] = None
        
        logger.debug(f"Initialized TerraformDiffGenerator with plan: {config.plan_file}")
    
    def run_command(
        self,
        cmd: List[str],
        timeout: Optional[int] = None,
        description: str = ""
    ) -> Optional[str]:
        """
        Safely execute a subprocess command with timeout and error handling.
        
        Args:
            cmd: Command to execute as list
            timeout: Timeout in seconds (uses config.command_timeout if None)
            description: Human-readable description of the command
            
        Returns:
            Command stdout output or None if failed
        """
        timeout = timeout or self.config.command_timeout
        description = description or ' '.join(cmd)
        
        try:
            logger.debug(f"Running command: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False
            )
            
            if result.returncode != 0:
                logger.error(
                    f"{description} failed with exit code {result.returncode}\n"
                    f"STDERR: {result.stderr[:500]}"  # Limit stderr output
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
    
    def load_and_parse_plan(self) -> Dict[str, Any]:
        """
        Load and parse Terraform plan file (JSON or binary).
        
        Returns:
            Parsed Terraform plan as dictionary
            
        Raises:
            FileNotFoundError: If plan file not found
            json.JSONDecodeError: If plan JSON is invalid
        """
        logger.info(f"Loading Terraform plan from: {self.config.plan_file}")
        
        # Try to read as JSON first
        try:
            with open(self.config.plan_file, "r", encoding="utf-8") as f:
                tf_json = json.load(f)
            
            if "resource_changes" in tf_json:
                logger.info("✅ Plan loaded as JSON directly")
                self.json_plan_path = self.config.plan_file
                return tf_json
        except json.JSONDecodeError as e:
            logger.debug(f"Not a valid JSON file (line {e.lineno}): {e.msg}")
        except UnicodeDecodeError:
            logger.debug("File is not UTF-8 encoded, likely a binary plan")
        except Exception as e:
            logger.error(f"Error reading plan file: {e}")
            raise
        
        # Binary plan file - convert to JSON using terraform show
        logger.info("Converting binary plan to JSON using 'terraform show'...")
        original_dir = os.getcwd()
        
        try:
            os.chdir(self.config.terraform_dir)
            
            stdout = self.run_command(
                ["terraform", "show", "-json", str(self.config.plan_file.absolute())],
                timeout=self.config.command_timeout,
                description="terraform show"
            )
            
            if not stdout:
                raise RuntimeError("Failed to convert binary plan using 'terraform show'")
            
            try:
                tf_json = json.loads(stdout)
            except json.JSONDecodeError as e:
                raise json.JSONDecodeError(
                    f"terraform show output is not valid JSON: {e.msg}",
                    e.doc,
                    e.pos
                )
            
            # Save temporary JSON for infracost
            with tempfile.NamedTemporaryFile(
                suffix=".json",
                delete=False,
                mode='w',
                encoding='utf-8'
            ) as tmp:
                json.dump(tf_json, tmp)
                self.json_plan_path = Path(tmp.name)
                logger.debug(f"Saved temporary JSON plan to: {self.json_plan_path}")
            
            return tf_json
        
        except Exception as e:
            logger.error(f"Failed to parse plan file: {e}")
            raise
        finally:
            os.chdir(original_dir)
    
    def get_infracost_data(self) -> Dict[str, Any]:
        """
        Get cost impact data from Infracost.
        
        Returns:
            Dictionary with cost data or empty dict if Infracost unavailable
        """
        logger.info("Calculating cloud cost impact using Infracost...")
        
        # Check if Infracost is available
        version_output = self.run_command(
            ["infracost", "--version"],
            timeout=10,
            description="infracost --version"
        )
        
        if not version_output:
            logger.warning("Infracost CLI not available. Skipping cost analysis.")
            return {}
        
        logger.debug(f"Infracost version: {version_output.strip()}")
        
        # Check for API key
        if not os.getenv("INFRACOST_API_KEY"):
            logger.warning(
                "INFRACOST_API_KEY environment variable not set. "
                "Cost details may be incomplete. See https://www.infracost.io/docs"
            )
        
        if not self.json_plan_path:
            logger.warning("No JSON plan available for Infracost analysis")
            return {}
        
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp_json:
            infracost_json_path = tmp_json.name
        
        try:
            cmd = [
                "infracost", "breakdown",
                "--path", str(self.json_plan_path),
                #"--path", ".",
                "--format", "json",
                "--out-file", infracost_json_path
            ]
            
            output = self.run_command(
                cmd,
                timeout=self.config.command_timeout,
                description="infracost breakdown"
            )

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
                    r.get("name", ""): r
                    for r in past_resources
                    if r.get("name")
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
                            "components": res.get("costComponents", [])
                        }
            
            logger.info(f"✅ Infracost analysis complete: {len(resource_costs)} resources")
            
            return {
                "overall_diff": float(cost_data.get("diffTotalMonthlyCost", 0.0)),
                "overall_past": float(cost_data.get("pastTotalMonthlyCost", 0.0)),
                "overall_current": float(cost_data.get("totalMonthlyCost", 0.0)),
                "currency": cost_data.get("currency", "USD"),
                "resources": resource_costs
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
    
    def calculate_risk(self, resource_type: str, action: str) -> str:
        """
        Calculate risk level for a resource change.
        
        Args:
            resource_type: Terraform resource type
            action: Change action (create, update, delete, replace)
            
        Returns:
            Risk level (critical, high, medium, low)
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
    
    def categorize_resource(self, resource_type: str) -> str:
        """
        Categorize resource by type.
        
        Args:
            resource_type: Terraform resource type
            
        Returns:
            Category (security, network, compute, database, container, storage, general)
        """
        categories = {
            "security": ["iam", "policy", "security", "firewall", "role"],
            "network": ["network", "subnet", "vpc", "gateway", "route", "proxy"],
            "compute": ["instance", "vm", "compute", "server"],
            "database": ["db", "database", "sql"],
            "container": ["kubernetes", "cluster", "container"],
            "storage": ["bucket", "storage", "disk"]
        }
        
        resource_lower = resource_type.lower()
        for category, keywords in categories.items():
            if any(k in resource_lower for k in keywords):
                return category
        
        return "general"
    
    def extract_changes(self) -> Dict[str, Any]:
        """
        Extract and analyze changes from Terraform plan.
        
        Returns:
            Dictionary with changes, summary, and cost data
        """
        logger.info("Extracting changes from Terraform plan...")
        
        tf_json = self.load_and_parse_plan()
        self.resource_mapper.parse_resource_references(tf_json)
        cost_impact = self.get_infracost_data()
        
        changes: List[Dict[str, Any]] = []
        
        for resource in tf_json.get("resource_changes", []):
            try:
                actions = resource.get("change", {}).get("actions", [])
                if not actions or actions[0] == "no-op":
                    continue
                
                action = actions[0]
                
                # Handle replace which comes as ['delete', 'create']
                if len(actions) > 1 and "create" in actions and "delete" in actions:
                    action = "replace"
                
                resource_type = resource.get("type", "unknown")
                address = resource.get("address", "unknown")
                
                # Find cost data for this resource
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
                    "risk": self.calculate_risk(resource_type, action),
                    "category": self.categorize_resource(resource_type),
                    "affected_resources": list(
                        self.resource_mapper.find_affected_resources(address)
                    ),
                    "costs": {
                        "monthly_cost": res_cost.get("monthly_cost", 0.0),
                        "past_cost": res_cost.get("past_cost", 0.0),
                        "diff_cost": res_cost.get("diff_cost", 0.0),
                        "currency": cost_impact.get("currency", "USD")
                    }
                })
            
            except (KeyError, TypeError, AttributeError) as e:
                logger.warning(f"Error processing resource {resource.get('address', 'unknown')}: {e}")
                continue
        
        # Calculate summary
        summary = {
            "total": len(changes),
            "create": sum(1 for c in changes if c["action"] in ["create", "replace"]),
            "update": sum(1 for c in changes if c["action"] == "update"),
            "delete": sum(1 for c in changes if c["action"] in ["delete", "replace"]),
            "providers": list(set(c["provider"] for c in changes))
        }
        
        logger.info(
            f"✅ Extracted {summary['total']} changes: "
            f"{summary['create']} creates, {summary['update']} updates, {summary['delete']} deletes"
        )
        
        return {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "summary": summary,
            "changes": changes,
            "costs": {
                "overall_diff": cost_impact.get("overall_diff", 0.0),
                "overall_past": cost_impact.get("overall_past", 0.0),
                "overall_current": cost_impact.get("overall_current", 0.0),
                "currency": cost_impact.get("currency", "USD")
            }
        }
    
    def get_llm_explanation(self, changes_data: Dict[str, Any]) -> str:
        """
        Get LLM-based architecture review of changes.
        
        Args:
            changes_data: Dictionary with extracted changes
            
        Returns:
            LLM explanation or error message
        """
        if not HAS_REQUESTS:
            logger.warning("requests library not installed, skipping LLM analysis")
            return "LLM explanation unavailable (requests library not installed)"
        
        # Build resource details for LLM
        resource_details = []
        for c in changes_data["changes"]:
            if c["action"] != "read":
                resource_details.append(
                    f"[{c['action'].upper()}] {c['address']} "
                    f"(Type: {c['type']}, Risk: {c['risk']})"
                )
        
        # Truncate to protect context window
        details_str = "\n".join(resource_details[:40])
        if len(resource_details) > 40:
            details_str += f"\n... and {len(resource_details) - 40} additional changes omitted for brevity."
        
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
            logger.debug(f"Sending LLM request to {self.config.ollama_url}")
            response = requests.post(
                f"{self.config.ollama_url}/api/generate",
                json={
                    "model": self.config.llm_model,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.1
                },
                timeout=self.config.command_timeout
            )
            
            if response.status_code == 200:
                result = response.json().get("response", "No analysis generated")
                logger.info("✅ LLM analysis completed")
                return result
            
            error_msg = f"LLM analysis failed (HTTP {response.status_code})"
            logger.error(f"{error_msg}: {response.text[:200]}")
            return error_msg
        
        except requests.exceptions.Timeout:
            error_msg = f"LLM request timed out after {self.config.command_timeout}s"
            logger.error(error_msg)
            return error_msg
        except requests.exceptions.ConnectionError as e:
            error_msg = f"Could not connect to Ollama at {self.config.ollama_url}"
            logger.error(f"{error_msg}: {e}")
            return error_msg
        except requests.exceptions.RequestException as e:
            logger.error(f"LLM request failed: {e}")
            return f"LLM analysis unavailable: {str(e)}"
        except Exception as e:
            logger.error(f"Unexpected error during LLM analysis: {e}")
            return f"LLM analysis failed: {str(e)}"
    
    def generate_diff_html(self, before: Optional[Dict], after: Optional[Dict]) -> str:
        """
        Generate HTML diff between before and after states.
        
        Args:
            before: Before state (dict or None)
            after: After state (dict or None)
            
        Returns:
            HTML formatted diff
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
            numlines=3
        )
    
    def generate_html_report(self, changes_data: Dict[str, Any], llm_explanation: str = "") -> str:
        """
        Generate complete HTML report with changes and analysis.
        
        Args:
            changes_data: Dictionary with extracted changes
            llm_explanation: LLM analysis (optional)
            
        Returns:
            HTML content as string
        """
        logger.info("Generating HTML report...")
        
        changes_rows = []
        action_colors = self.config.COLORS
        risk_colors = self.config.RISK_COLORS
        action_icons = {
            "create": "➕",
            "update": "✏️",
            "delete": "🗑️",
            "replace": "🔄"
        }
        
        # Cap table rows to prevent browser lag (PHASE 1: CONFIGURABLE)
        for change in changes_data["changes"][:self.config.max_table_rows]:
            action = change["action"]
            color = action_colors.get(action, "#6c757d")
            icon = action_icons.get(action, "•")
            
            costs = change.get("costs", {})
            components = costs.get("components", [])
            diff_cost = costs.get("diff_cost", 0.0)
            monthly_cost = costs.get("monthly_cost", 0.0)
            
            # Escape all user-provided data (PHASE 1: HTML INJECTION FIX)
            address_escaped = html.escape(change["address"])
            type_escaped = html.escape(change["type"])
            provider_escaped = html.escape(change["provider"])
            category_escaped = html.escape(change["category"])
            risk_escaped = html.escape(change["risk"])
            
            diff_html = ""
            cost_str = ""
            component_html = ""
            affected_str = ""
            
            # Generate diff HTML if before/after states available
            if action in ["update", "replace"] and change["before"] and change["after"]:
                diff_html = f"""
                <details>
                    <summary style="cursor:pointer;color:#667eea;font-weight:bold;">View JSON Diff</summary>
                    <div style="overflow:auto;margin-top:10px;">{self.generate_diff_html(change["before"], change["after"])}</div>
                </details>
                """
            
            # Generate cost impact HTML
            if monthly_cost > 0 or diff_cost != 0:
                badge_bg = "#ffebee" if diff_cost > 0 else "#e8f5e9" if diff_cost < 0 else "#e3f2fd"
                text_color = "#c62828" if diff_cost > 0 else "#2e7d32" if diff_cost < 0 else "#1565c0"
                sign = "+" if diff_cost > 0 else ""
                
                cost_str = f"""
                <div style="margin-top:10px;background:{badge_bg};padding:8px;border-radius:6px;font-size:12px;">
                    <div style="font-weight:bold;color:{text_color};">💰 Cost Impact: {sign}${diff_cost:.2f}/mo (Total: ${monthly_cost:.2f})</div>
                </div>
                """
            if components:
                component_rows = ""

                for component in components:
                    name = component.get("name", "Unknown")
                    cost = component.get("monthlyCost", "0")

                    component_rows += f"""
                    <tr>
                        <td style="padding:4px;">{html.escape(name)}</td>
                        <td style="padding:4px;font-weight:bold;">${cost}</td>
                    </tr>
                    """

                component_html = f"""
                <details style="margin-top:8px;">
                    <summary style="cursor:pointer;color:#444;font-size:12px;">
                        📊 Cost Breakdown
                    </summary>

                    <table style="width:100%;margin-top:8px;font-size:12px;background:#fafafa;">
                        {component_rows}
                    </table>
                </details>
                """
            
            # Generate affected resources HTML
            if change.get("affected_resources"):
                affected_list = "".join(
                    f"<li>{html.escape(r)}</li>"  # PHASE 1: ESCAPE HTML
                    for r in change["affected_resources"][:5]
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
                <td style="padding:12px;">{type_escaped}<br><br><span style="background:#6c757d;color:white;padding:3px 8px;border-radius:10px;font-size:10px;">{category_escaped}</span></td>
                <td style="padding:12px;">{provider_escaped}<br><br><span style="background:{risk_colors.get(change['risk'], '#6c757d')};color:white;padding:4px 8px;border-radius:12px;font-size:11px;font-weight:bold;">{risk_escaped}</span></td>
                <td style="padding:12px;">
                    {diff_html}
                    {cost_str}
                    {component_html}
                    {affected_str}
                </td>
            </tr>
            """)
        
        changes_table = "".join(changes_rows)
        summary = changes_data["summary"]
        
        # Convert markdown to HTML if available
        llm_html = ""
        if llm_explanation:
            try:
                import markdown
                llm_html = markdown.markdown(llm_explanation)
            except ImportError:
                # Fallback to simple HTML conversion
                llm_html = html.escape(llm_explanation).replace('\n', '<br>')
        
        # Escape timestamp and plan file for display (PHASE 1: HTML INJECTION FIX)
        timestamp_escaped = html.escape(changes_data["timestamp"])
        plan_file_escaped = html.escape(str(self.config.plan_file))
        
        html_content = f"""
<!DOCTYPE html>
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
        <input type="text" id="searchInput" placeholder="Search resources..." style="width:100%;padding:12px;border:1px solid #ccc;border-radius:4px;" onkeyup="filterTable()">
    </div>

    <div style="overflow:auto; padding:20px;">
        <table>
            <thead><tr><th>Action</th><th>Address</th><th>Type</th><th>Provider / Risk</th><th>Impact Details</th></tr></thead>
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
</html>
"""
        
        logger.info("✅ HTML report generated successfully")
        return html_content
    
    def cleanup(self) -> None:
        """Clean up temporary files created during execution."""
        if self.json_plan_path and self.json_plan_path != self.config.plan_file:
            try:
                self.json_plan_path.unlink()
                logger.debug(f"Cleaned up temporary file: {self.json_plan_path}")
            except OSError as e:
                logger.warning(f"Could not clean up temp JSON plan: {e}")
    
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
            
            # Extract changes from plan
            changes = self.extract_changes()
            
            # Get LLM explanation if enabled
            llm_explanation = ""
            if self.config.enable_llm and HAS_REQUESTS:
                logger.info("🤖 Generating LLM architecture review...")
                llm_explanation = self.get_llm_explanation(changes)
            
            # Generate HTML report
            logger.info("📄 Generating HTML report...")
            html_content = self.generate_html_report(changes, llm_explanation)
            
            # Write to output file
            output_path = self.config.output_file
            output_path.write_text(html_content, encoding="utf-8")
            logger.info(f"✅ Report generated: {output_path.absolute()}")
            
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
            self.cleanup()


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main() -> int:
    """
    Main entry point for the script.
    
    Returns:
        0 if successful, 1 if failed
    """
    parser = argparse.ArgumentParser(
        description="Enhanced Terraform HTML Diff Dashboard with Cost Analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 gemini_tf_differ.py --plan-file infra.tfplan --terraform-dir .
  python3 gemini_tf_differ.py --plan-file plan.json --output report.html --no-llm
  python3 gemini_tf_differ.py --plan-file plan.tfplan --log-file analyze.log
        """
    )
    
    parser.add_argument(
        "--plan-file",
        default="plan.json",
        help="Path to terraform plan file (binary .tfplan or .json)"
    )
    parser.add_argument(
        "--terraform-dir",
        default=".",
        help="Path to terraform working directory (required for binary .tfplan)"
    )
    parser.add_argument(
        "--output",
        default="terraform-plan-report.html",
        help="Output HTML file name"
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Disable LLM analysis (faster)"
    )
    parser.add_argument(
        "--llm-model",
        default="llama3.1",
        help="Ollama LLM model name"
    )
    parser.add_argument(
        "--ollama-url",
        default="http://localhost:11434",
        help="Ollama service URL"
    )
    parser.add_argument(
        "--log-file",
        default=None,
        help="Optional log file path"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    setup_logger(
        level=log_level,
        log_file=args.log_file
    )
    
    logger.info("Terraform Plan Analyzer - Production Ready Edition")
    logger.info(f"Python version: {sys.version}")
    
    try:
        # Create configuration
        config = TerraformDiffConfig.from_cli_args(args)
        
        # Validate configuration
        config.validate()
        
        # Run generator
        generator = TerraformDiffGenerator(config)
        success = generator.run()
        
        if success:
            logger.info("=" * 70)
            logger.info("✅ Terraform plan analysis completed successfully")
            logger.info("=" * 70)
            return 0
        else:
            logger.error("=" * 70)
            logger.error("❌ Terraform plan analysis failed")
            logger.error("=" * 70)
            return 1
    
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        logger.error(f"Configuration error: {e}")
        logger.error("Please check your inputs and try again")
        return 1
    except KeyboardInterrupt:
        logger.warning("Analysis interrupted by user")
        return 1
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())


