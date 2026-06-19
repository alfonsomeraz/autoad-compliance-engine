"""Load the YAML rule catalog into `Rule` objects.

Rules are authored as data in the top-level `rules/` directory. In Milestone 1
these same rules move into the database as versioned rows with `ruleset_version`
pinning; for now the YAML files are the source of truth loaded at runtime.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from app.rules.schema import Rule

# repo_root/rules — authoring source for the catalog.
RULES_DIR = Path(__file__).resolve().parents[2] / "rules"


def load_catalog(rules_dir: Path | str = RULES_DIR) -> list[Rule]:
    """Parse every *.yaml file in `rules_dir` into a list of Rule objects."""
    directory = Path(rules_dir)
    rules: list[Rule] = []
    for path in sorted(directory.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text()) or []
        rules.extend(Rule.model_validate(entry) for entry in raw)
    return rules
