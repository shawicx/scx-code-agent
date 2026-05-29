import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from dotenv import load_dotenv


@dataclass
class ProviderConfig:
    name: str = "anthropic"
    model: str = "claude-sonnet-4-20250514"
    api_key: str = ""
    base_url: Optional[str] = None
    timeout: int = 60


@dataclass
class ReviewConfig:
    max_workers: int = 5
    context_lines: int = 3
    skip_dirs: List[str] = field(default_factory=list)
    skip_extensions: List[str] = field(default_factory=list)


@dataclass
class OutputConfig:
    default_format: str = "markdown"
    default_path: str = "dist/report.md"


@dataclass
class GitHubConfig:
    token: str = ""


@dataclass
class Config:
    provider: ProviderConfig = field(default_factory=ProviderConfig)
    review: ReviewConfig = field(default_factory=ReviewConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    github: GitHubConfig = field(default_factory=GitHubConfig)


_ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _substitute_env(value: Any) -> Any:
    """Replace ${VAR} references in values with environment variables."""
    if isinstance(value, str):
        return _ENV_VAR_PATTERN.sub(lambda m: os.getenv(m.group(1), m.group(0)), value)
    elif isinstance(value, dict):
        return {k: _substitute_env(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_substitute_env(item) for item in value]
    return value


_CONFIG_CANDIDATES = [
    ".scx-code-agent.yaml",
    "scx-code-agent.yaml",
    ".scx-code-agent.yml",
    "scx-code-agent.yml",
]


def _find_project_config() -> Optional[Path]:
    """Find configuration file in current directory."""
    for name in _CONFIG_CANDIDATES:
        p = Path(name)
        if p.exists():
            return p
    return None


def _find_global_config() -> Optional[Path]:
    """Find global configuration file in home directory."""
    for name in _CONFIG_CANDIDATES:
        p = Path.home() / name
        if p.exists():
            return p
    return None


def _read_yaml(path: Path) -> Optional[Dict]:
    """Read and env-substitute a YAML file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return _substitute_env(data) if data else {}
    except Exception as e:
        print(f"Warning: Failed to load config file {path}: {e}")
        return None


def _deep_merge(base: Dict, override: Dict) -> Dict:
    """Recursively merge override into base. Override values win."""
    merged = base.copy()
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config() -> Config:
    """Load configuration (priority: env vars > project config > global config > defaults)."""
    load_dotenv()

    # Load global config first, then project config overrides it
    config_data: Dict = {}
    global_path = _find_global_config()
    if global_path:
        global_data = _read_yaml(global_path)
        if global_data:
            config_data = global_data
    project_path = _find_project_config()
    if project_path:
        project_data = _read_yaml(project_path)
        if project_data:
            config_data = _deep_merge(config_data, project_data)

    # Extract provider configuration
    provider_config = config_data.get("provider", {})
    provider_name = os.getenv("LLM_PROVIDER", provider_config.get("name", "anthropic"))
    provider_model = os.getenv("LLM_MODEL", provider_config.get("model", "claude-sonnet-4-20250514"))
    provider_key = os.getenv("LLM_API_KEY", provider_config.get("api_key", ""))
    provider_base_url = os.getenv("LLM_BASE_URL", provider_config.get("base_url"))

    # Extract review configuration
    review_config = config_data.get("review", {})

    # Extract output configuration
    output_config = config_data.get("output", {})

    # Extract github configuration
    github_config = config_data.get("github", {})
    github_token = os.getenv("GITHUB_TOKEN", github_config.get("token", ""))

    return Config(
        provider=ProviderConfig(
            name=provider_name,
            model=provider_model,
            api_key=provider_key,
            base_url=provider_base_url,
        ),
        review=ReviewConfig(
            max_workers=review_config.get("max_workers", 5),
            context_lines=review_config.get("context_lines", 3),
            skip_dirs=review_config.get("skip_dirs", []),
            skip_extensions=review_config.get("skip_extensions", []),
        ),
        output=OutputConfig(
            default_format=output_config.get("default_format", "markdown"),
            default_path=output_config.get("default_path", "dist/report.md"),
        ),
        github=GitHubConfig(
            token=github_token,
        ),
    )
