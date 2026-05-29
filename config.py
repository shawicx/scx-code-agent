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
class Config:
    provider: ProviderConfig = field(default_factory=ProviderConfig)
    review: ReviewConfig = field(default_factory=ReviewConfig)
    output: OutputConfig = field(default_factory=OutputConfig)


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


def find_config_file() -> Optional[Path]:
    """Find configuration file in current directory."""
    candidates = [
        Path(".code-agent.yaml"),
        Path("code-agent.yaml"),
        Path(".code-agent.yml"),
        Path("code-agent.yml"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def load_config_file(config_path: Optional[Path] = None) -> Optional[Dict]:
    """Load YAML configuration file."""
    if config_path is None:
        config_path = find_config_file()

    if config_path is None or not config_path.exists():
        return None

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return _substitute_env(data) if data else {}
    except Exception as e:
        print(f"Warning: Failed to load config file {config_path}: {e}")
        return None


def load_config() -> Config:
    """Load configuration (priority: file > env vars > defaults)."""
    load_dotenv()

    # Load config file
    config_data = load_config_file()
    if config_data is None:
        config_data = {}

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
    )
