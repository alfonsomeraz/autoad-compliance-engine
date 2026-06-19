"""Load the YAML rule catalog into `RuleSpec` objects.

Rules are authored as data in the top-level `rules/` directory. This loader
reads the YAML authoring source; the rule DB sync (see app/rules/sync.py) turns
these specs into versioned `rule` rows pinned by `ruleset_version`.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from app.rules.schema import RuleSpec

# repo_root/rules — authoring source for the catalog.
RULES_DIR = Path(__file__).resolve().parents[2] / "rules"


def load_catalog(rules_dir: Path | str = RULES_DIR) -> list[RuleSpec]:
    """Parse every *.yaml file in `rules_dir` into a list of RuleSpec objects."""
    directory = Path(rules_dir)
    rules: list[RuleSpec] = []
    for path in sorted(directory.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text()) or []
        rules.extend(RuleSpec.model_validate(entry) for entry in raw)
    return rules
