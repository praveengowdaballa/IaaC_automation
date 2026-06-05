"""
scripts/resource_mapper.py
Maps Terraform resource dependencies and relationships.
"""

from collections import defaultdict
from typing import Any, Dict, Set

from scripts.logger import logger


class TerraformResourceMapper:
    """Maps Terraform resource dependencies and relationships."""

    def __init__(self) -> None:
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

            logger.debug(
                f"Parsed {len(self.resources)} resources and their dependencies"
            )
        except (KeyError, TypeError) as e:
            logger.warning(
                f"Error parsing resource references: {e}. "
                f"Continuing without full dependency mapping."
            )

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
