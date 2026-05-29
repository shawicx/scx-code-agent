from pathlib import Path
from unittest.mock import patch

from config import find_config_file, load_config, load_config_file


class TestConfigLoading:
    @patch("config.load_dotenv")
    def test_load_config_without_file(self, mock_load_dotenv, tmp_path, monkeypatch):
        """无配置文件时使用默认值"""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        monkeypatch.delenv("LLM_MODEL", raising=False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.delenv("LLM_BASE_URL", raising=False)

        config = load_config()

        assert config.provider.name == "anthropic"
        assert config.provider.model == "claude-sonnet-4-20250514"

    def test_load_config_with_env_vars(self, monkeypatch):
        """环境变量覆盖默认值"""
        monkeypatch.setenv("LLM_PROVIDER", "deepseek")
        monkeypatch.setenv("LLM_MODEL", "deepseek-v4-flash")
        monkeypatch.setenv("LLM_API_KEY", "test-key-123")

        config = load_config()

        assert config.provider.name == "deepseek"
        assert config.provider.model == "deepseek-v4-flash"
        assert config.provider.api_key == "test-key-123"

    def test_find_config_file_priorities(self, tmp_path, monkeypatch):
        """配置文件查找优先级"""
        (tmp_path / ".scx-code-agent.yaml").write_text("test: true")
        monkeypatch.chdir(tmp_path)

        assert find_config_file() == Path(".scx-code-agent.yaml")

    def test_load_config_file_with_env_substitution(self, tmp_path, monkeypatch):
        """环境变量替换 ${VAR} 语法"""
        config_file = tmp_path / ".scx-code-agent.yaml"
        config_file.write_text("""
provider:
  name: test-provider
  api_key: ${TEST_API_KEY}
""")
        monkeypatch.setenv("TEST_API_KEY", "secret-from-env")
        monkeypatch.chdir(tmp_path)

        data = load_config_file(config_file)
        assert data["provider"]["api_key"] == "secret-from-env"

    def test_config_priority_env_over_file(self, tmp_path, monkeypatch):
        """环境变量优先级高于配置文件"""
        config_file = tmp_path / ".scx-code-agent.yaml"
        config_file.write_text("""
provider:
  name: file-provider
  model: file-model
""")
        monkeypatch.setenv("LLM_PROVIDER", "env-provider")
        monkeypatch.chdir(tmp_path)

        config = load_config()
        assert config.provider.name == "env-provider"
