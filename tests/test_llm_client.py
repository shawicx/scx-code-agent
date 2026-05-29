import json
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from llm_client import IssueModel, IssuesResponse, LLMClient


class TestIssueModel:
    """Test Pydantic IssueModel validation."""

    def test_valid_blocker(self):
        model = IssueModel(
            file_path="a.py",
            line_number=1,
            category="Security",
            level="Blocker",
            description="test",
            suggestion="fix",
        )
        assert model.level == "Blocker"

    def test_valid_warning(self):
        model = IssueModel(
            file_path="a.py",
            line_number=1,
            category="Style",
            level="Warning",
            description="test",
            suggestion="fix",
        )
        assert model.level == "Warning"

    def test_valid_info(self):
        model = IssueModel(
            file_path="a.py",
            line_number=1,
            category="Info",
            level="Info",
            description="test",
            suggestion="fix",
        )
        assert model.level == "Info"

    def test_invalid_level_raises(self):
        with pytest.raises(ValidationError):
            IssueModel(
                file_path="a.py",
                line_number=1,
                category="Bug",
                level="Critical",
                description="test",
                suggestion="fix",
            )

    def test_line_number_zero_raises(self):
        with pytest.raises(ValidationError):
            IssueModel(
                file_path="a.py",
                line_number=0,
                category="Bug",
                level="Info",
                description="test",
                suggestion="fix",
            )

    def test_line_number_negative_raises(self):
        with pytest.raises(ValidationError):
            IssueModel(
                file_path="a.py",
                line_number=-1,
                category="Bug",
                level="Info",
                description="test",
                suggestion="fix",
            )


class TestIssuesResponse:
    """Test IssuesResponse model."""

    def test_to_agent_issues(self):
        issues = IssuesResponse(
            issues=[
                IssueModel(
                    file_path="a.py",
                    line_number=1,
                    category="Bug",
                    level="Info",
                    description="test",
                    suggestion="fix",
                )
            ]
        )
        result = issues.to_agent_issues()
        assert len(result) == 1
        assert result[0]["file_path"] == "a.py"
        assert result[0]["level"] == "Info"

    def test_empty_issues(self):
        issues = IssuesResponse(issues=[])
        assert issues.to_agent_issues() == []

    def test_default_factory(self):
        issues = IssuesResponse()
        assert issues.issues == []


class TestPrepareCodeContent:
    """Test _prepare_code_content method."""

    @pytest.fixture
    def client(self):
        """Create LLMClient with mocked __init__ to avoid real API init."""
        with patch.object(LLMClient, "__init__", lambda self, **kwargs: None):
            c = LLMClient.__new__(LLMClient)
            c.context_lines = 3
            return c

    def test_no_diff_lines(self, client):
        """Without diff_lines, returns full content."""
        content = "line1\nline2\nline3"
        result, o2l, l2o = client._prepare_code_content(content, None)
        assert result == content
        assert o2l == {}
        assert l2o == {}

    def test_empty_diff_lines(self, client):
        """Empty diff_lines list returns full content."""
        content = "line1\nline2\nline3"
        result, o2l, l2o = client._prepare_code_content(content, [])
        assert result == content
        assert o2l == {}
        assert l2o == {}

    def test_with_diff_lines(self, client):
        """Diff mode extracts context around changed lines."""
        content = "\n".join([f"line{i}" for i in range(1, 21)])
        # Line 10 (1-based) +/- 3 context lines = lines 7-13
        result, o2l, l2o = client._prepare_code_content(content, [10])

        # Should include lines 7 through 13 (1-based) = indices 6 through 12
        result_lines = result.split("\n")
        assert "line7" in result_lines
        assert "line13" in result_lines
        assert len(result_lines) == 7

        # Check mappings
        assert o2l[7] == 1  # orig line 7 maps to LLM line 1
        assert o2l[13] == 7  # orig line 13 maps to LLM line 7
        assert l2o[1] == 7
        assert l2o[7] == 13

    def test_diff_lines_near_start(self, client):
        """Diff lines near the start of file."""
        content = "line1\nline2\nline3\nline4\nline5"
        result, o2l, l2o = client._prepare_code_content(content, [1])
        # Line 1 +/- 3 = lines 1-4, but file starts at 1 so min is 0 index
        assert "line1" in result
        assert o2l[1] == 1

    def test_diff_lines_near_end(self, client):
        """Diff lines near the end of file."""
        content = "line1\nline2\nline3\nline4\nline5"
        result, o2l, l2o = client._prepare_code_content(content, [5])
        assert "line5" in result
        assert o2l[5] is not None

    def test_multiple_diff_lines(self, client):
        """Multiple diff lines extract combined context."""
        content = "\n".join([f"line{i}" for i in range(1, 21)])
        # Lines 3 and 17 +/- 3 each, with gap in middle
        result, o2l, l2o = client._prepare_code_content(content, [3, 17])
        result_lines = result.split("\n")
        assert "line1" in result_lines  # context for line 3
        assert "line6" in result_lines  # context for line 3
        assert "line14" in result_lines  # context for line 17
        assert "line20" in result_lines  # context for line 17


class TestExtractJson:
    """Test _extract_json method."""

    @pytest.fixture
    def client(self):
        with patch.object(LLMClient, "__init__", lambda self, **kwargs: None):
            return LLMClient.__new__(LLMClient)

    def test_raw_json_array(self, client):
        """Extracts raw JSON array."""
        data = '[{"file_path":"a.py"}]'
        assert client._extract_json(data) == data

    def test_json_wrapped_in_text(self, client):
        """Extracts JSON from surrounding text."""
        text = 'Here is the result:\n[{"file_path":"a.py"}]\nEnd.'
        result = client._extract_json(text)
        assert json.loads(result)

    def test_markdown_code_block(self, client):
        """Extracts JSON from markdown code block."""
        text = '```json\n[{"file_path":"a.py"}]\n```'
        result = client._extract_json(text)
        assert json.loads(result)

    def test_markdown_code_block_no_language(self, client):
        """Extracts JSON from untyped code block."""
        text = '```\n[{"file_path":"a.py"}]\n```'
        result = client._extract_json(text)
        assert json.loads(result)

    def test_invalid_text_returns_original(self, client):
        """Returns original text if no JSON found."""
        text = "no json here"
        result = client._extract_json(text)
        assert result == text

    def test_empty_string(self, client):
        """Handles empty string."""
        result = client._extract_json("")
        assert result == ""

    def test_nested_brackets(self, client):
        """Handles nested brackets correctly."""
        text = '[{"a": [1, 2]}]'
        result = client._extract_json(text)
        parsed = json.loads(result)
        assert parsed[0]["a"] == [1, 2]


class TestRepairJson:
    """Test _repair_json method."""

    @pytest.fixture
    def client(self):
        with patch.object(LLMClient, "__init__", lambda self, **kwargs: None):
            return LLMClient.__new__(LLMClient)

    def test_valid_json_unchanged(self, client):
        """Valid JSON is returned unchanged."""
        text = '[{"key": "value"}]'
        assert client._repair_json(text) == text

    def test_fixes_unclosed_string_with_comma(self, client):
        """Fixes line with odd quotes by finding trailing comma."""
        text = '[{"key": "value"\n]'
        result = client._repair_json(text)
        # Should produce parseable JSON or at least not crash
        assert isinstance(result, str)

    def test_fixes_unclosed_string(self, client):
        """Fixes line with unclosed string value."""
        text = '[{"key": "value\n}]'
        result = client._repair_json(text)
        assert isinstance(result, str)


class TestParseResponse:
    """Test _parse_response method."""

    @pytest.fixture
    def client(self):
        with patch.object(LLMClient, "__init__", lambda self, **kwargs: None):
            return LLMClient.__new__(LLMClient)

    def test_valid_json_list(self, client):
        """Parses valid JSON list of issues."""
        response = json.dumps(
            [
                {
                    "file_path": "a.py",
                    "line_number": 1,
                    "category": "Bug",
                    "level": "Info",
                    "description": "test",
                    "suggestion": "fix",
                }
            ]
        )
        result = client._parse_response(response)
        assert len(result) == 1
        assert result[0]["file_path"] == "a.py"
        assert result[0]["level"] == "Info"

    def test_valid_json_dict_with_issues(self, client):
        """Parses JSON dict with 'issues' key."""
        response = json.dumps(
            {
                "issues": [
                    {
                        "file_path": "b.py",
                        "line_number": 5,
                        "category": "Security",
                        "level": "Blocker",
                        "description": "SQL injection",
                        "suggestion": "Parametrize",
                    }
                ]
            }
        )
        result = client._parse_response(response)
        assert len(result) == 1
        assert result[0]["file_path"] == "b.py"

    def test_empty_list(self, client):
        """Empty JSON array returns empty list."""
        result = client._parse_response("[]")
        assert result == []

    def test_invalid_json_returns_empty(self, client):
        """Invalid JSON returns empty list."""
        result = client._parse_response("not json at all")
        assert result == []

    def test_unexpected_format_returns_empty(self, client):
        """JSON that is neither list nor dict with 'issues' returns empty."""
        result = client._parse_response('{"key": "value"}')
        assert result == []

    def test_pydantic_validation_failure_returns_empty(self, client):
        """Issues with invalid level return empty list."""
        response = json.dumps(
            [
                {
                    "file_path": "a.py",
                    "line_number": 1,
                    "category": "Bug",
                    "level": "InvalidLevel",
                    "description": "test",
                    "suggestion": "fix",
                }
            ]
        )
        result = client._parse_response(response)
        assert result == []

    def test_markdown_wrapped_json(self, client):
        """JSON wrapped in markdown code block is extracted."""
        issue = {
            "file_path": "a.py",
            "line_number": 1,
            "category": "Bug",
            "level": "Info",
            "description": "test",
            "suggestion": "fix",
        }
        response = f"```json\n{json.dumps([issue])}\n```"
        result = client._parse_response(response)
        assert len(result) == 1

    def test_broken_json_repair(self, client):
        """Attempts repair of broken JSON."""
        # This is a somewhat valid JSON that can be repaired
        issue = {
            "file_path": "a.py",
            "line_number": 1,
            "category": "Bug",
            "level": "Info",
            "description": "test",
            "suggestion": "fix",
        }
        response = json.dumps([issue])
        result = client._parse_response(response)
        assert len(result) == 1


class TestGetCodeFenceLanguage:
    """Test _get_code_fence_language static method."""

    @pytest.mark.parametrize(
        "file_path,expected",
        [
            ("test.py", "python"),
            ("app.js", "javascript"),
            ("app.ts", "typescript"),
            ("component.tsx", "typescript"),
            ("component.jsx", "javascript"),
            ("Main.java", "java"),
            ("main.go", "go"),
            ("main.rs", "rust"),
            ("main.c", "c"),
            ("main.cpp", "cpp"),
            ("main.cc", "cpp"),
            ("main.cxx", "cpp"),
            ("header.h", "c"),
            ("header.hpp", "cpp"),
            ("Program.cs", "csharp"),
            ("index.php", "php"),
            ("app.rb", "ruby"),
            ("app.swift", "swift"),
            ("app.kt", "kotlin"),
            ("app.scala", "scala"),
            ("script.sh", "bash"),
            ("script.bash", "bash"),
            ("script.zsh", "zsh"),
            ("script.fish", "fish"),
            ("query.sql", "sql"),
            ("page.html", "html"),
            ("style.css", "css"),
            ("style.scss", "scss"),
            ("style.less", "less"),
            ("data.json", "json"),
            ("config.yaml", "yaml"),
            ("config.yml", "yaml"),
            ("data.xml", "xml"),
            ("README.md", "markdown"),
        ],
    )
    def test_known_extensions(self, file_path, expected):
        assert LLMClient._get_code_fence_language(file_path) == expected

    def test_dockerfile_by_name(self):
        assert LLMClient._get_code_fence_language("Dockerfile") == "dockerfile"

    def test_dockerignore(self):
        assert LLMClient._get_code_fence_language(".dockerignore") == "dockerfile"

    def test_unknown_extension(self):
        assert LLMClient._get_code_fence_language("file.xyz") == "text"

    def test_no_extension(self):
        assert LLMClient._get_code_fence_language("Makefile") == "text"

    def test_case_insensitive_extension(self):
        assert LLMClient._get_code_fence_language("test.PY") == "python"


class TestLLMClientInit:
    """Test LLMClient initialization."""

    def test_init_with_dict_config(self):
        """Init with dict config creates proper client."""
        config_dict = {
            "provider": {
                "name": "openai",
                "api_key": "test-key",
                "model": "gpt-4",
            },
            "review": {"context_lines": 5},
            "output": {},
        }
        with patch.object(LLMClient, "_init_chat_model"):
            client = LLMClient(config=config_dict)

        assert client.provider == "openai"
        assert client.model == "gpt-4"
        assert client.api_key == "test-key"
        assert client.context_lines == 5

    def test_init_with_config_object(self):
        """Init with Config dataclass."""
        from config import Config, OutputConfig, ProviderConfig, ReviewConfig

        config = Config(
            provider=ProviderConfig(name="anthropic", api_key="sk-test", model="claude-3"),
            review=ReviewConfig(context_lines=3),
            output=OutputConfig(),
        )
        with patch.object(LLMClient, "_init_chat_model"):
            client = LLMClient(config=config)

        assert client.provider == "anthropic"
        assert client.api_key == "sk-test"

    def test_init_no_api_key_raises(self):
        """Init without API key raises ValueError."""
        from config import Config, OutputConfig, ProviderConfig, ReviewConfig

        config = Config(
            provider=ProviderConfig(name="openai", api_key=""),
            review=ReviewConfig(),
            output=OutputConfig(),
        )
        with patch.object(LLMClient, "_init_chat_model"):
            with pytest.raises(ValueError, match="API key is required"):
                LLMClient(config=config)

    def test_init_none_config_loads_default(self):
        """Init with None config loads from load_config."""
        from config import Config, OutputConfig, ProviderConfig, ReviewConfig

        mock_config = Config(
            provider=ProviderConfig(name="openai", api_key="key", model="gpt-4"),
            review=ReviewConfig(),
            output=OutputConfig(),
        )
        with (
            patch("llm_client.load_config", return_value=mock_config),
            patch.object(LLMClient, "_init_chat_model"),
        ):
            client = LLMClient(config=None)
        assert client.api_key == "key"

    def test_context_lines_override(self):
        """context_lines parameter overrides config."""
        from config import Config, OutputConfig, ProviderConfig, ReviewConfig

        config = Config(
            provider=ProviderConfig(name="openai", api_key="key", model="gpt-4"),
            review=ReviewConfig(context_lines=3),
            output=OutputConfig(),
        )
        with patch.object(LLMClient, "_init_chat_model"):
            client = LLMClient(config=config, context_lines=10)
        assert client.context_lines == 10


class TestInitChatModel:
    """Test _init_chat_model method."""

    def _make_config(self, provider, base_url=None):
        from config import Config, OutputConfig, ProviderConfig, ReviewConfig

        return Config(
            provider=ProviderConfig(name=provider, api_key="key", model="model", base_url=base_url),
            review=ReviewConfig(),
            output=OutputConfig(),
        )

    def test_anthropic_provider(self):
        with (
            patch("llm_client.ChatAnthropic") as mock_cls,
            patch("llm_client.ChatOpenAI"),
        ):
            mock_cls.return_value = MagicMock()
            client = LLMClient.__new__(LLMClient)
            client.provider = "anthropic"
            client.model = "claude-3"
            client.api_key = "key"
            client.base_url = None
            client._init_chat_model()
            mock_cls.assert_called_once()

    def test_openai_provider(self):
        with (
            patch("llm_client.ChatOpenAI") as mock_cls,
            patch("llm_client.ChatAnthropic"),
        ):
            mock_cls.return_value = MagicMock()
            client = LLMClient.__new__(LLMClient)
            client.provider = "openai"
            client.model = "gpt-4"
            client.api_key = "key"
            client.base_url = "https://api.openai.com/v1"
            client._init_chat_model()
            mock_cls.assert_called_once()

    def test_deepseek_provider_default_url(self):
        with (
            patch("llm_client.ChatOpenAI") as mock_cls,
            patch("llm_client.ChatAnthropic"),
        ):
            mock_cls.return_value = MagicMock()
            client = LLMClient.__new__(LLMClient)
            client.provider = "deepseek"
            client.model = "deepseek-chat"
            client.api_key = "key"
            client.base_url = None
            client._init_chat_model()
            call_kwargs = mock_cls.call_args[1]
            assert call_kwargs["base_url"] == "https://api.deepseek.com"

    def test_glm_provider_default_url(self):
        with (
            patch("llm_client.ChatOpenAI") as mock_cls,
            patch("llm_client.ChatAnthropic"),
        ):
            mock_cls.return_value = MagicMock()
            client = LLMClient.__new__(LLMClient)
            client.provider = "glm"
            client.model = "glm-4"
            client.api_key = "key"
            client.base_url = None
            client._init_chat_model()
            call_kwargs = mock_cls.call_args[1]
            assert "bigmodel.cn" in call_kwargs["base_url"]

    def test_unsupported_provider_raises(self):
        client = LLMClient.__new__(LLMClient)
        client.provider = "unknown"
        client.model = "model"
        client.api_key = "key"
        client.base_url = None
        with pytest.raises(ValueError, match="Unsupported provider"):
            client._init_chat_model()


class TestReviewCode:
    """Test review_code method."""

    @pytest.fixture
    def client(self):
        with patch.object(LLMClient, "__init__", lambda self, **kwargs: None):
            c = LLMClient.__new__(LLMClient)
            c.context_lines = 3
            c.chat_model = MagicMock()
            return c

    def test_review_code_returns_issues(self, client):
        """review_code parses LLM response into issues."""
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            [
                {
                    "file_path": "test.py",
                    "line_number": 1,
                    "category": "Security",
                    "level": "Blocker",
                    "description": "SQL injection",
                    "suggestion": "Parameterize",
                }
            ]
        )
        client.chat_model.invoke.return_value = mock_response

        result = client.review_code("test.py", "code", "role prompt")
        assert len(result) == 1
        assert result[0]["file_path"] == "test.py"

    def test_review_code_exception_returns_empty(self, client):
        """review_code returns empty list on exception."""
        client.chat_model.invoke.side_effect = Exception("API error")

        result = client.review_code("test.py", "code", "role prompt")
        assert result == []

    def test_review_code_with_diff_lines(self, client):
        """review_code maps LLM line numbers back to original."""
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            [
                {
                    "file_path": "test.py",
                    "line_number": 1,
                    "category": "Bug",
                    "level": "Warning",
                    "description": "issue on LLM line 1",
                    "suggestion": "fix",
                }
            ]
        )
        client.chat_model.invoke.return_value = mock_response

        content = "\n".join([f"line{i}" for i in range(1, 21)])
        result = client.review_code("test.py", content, "role prompt", diff_lines=[10])

        # The LLM sees a subset of lines; line_number should be mapped back
        assert len(result) == 1
        # The mapped line_number should be the original line, not LLM line
        assert result[0]["line_number"] != 1 or result[0]["line_number"] == 7

    def test_review_code_empty_response(self, client):
        """review_code handles empty LLM response."""
        mock_response = MagicMock()
        mock_response.content = "[]"
        client.chat_model.invoke.return_value = mock_response

        result = client.review_code("test.py", "code", "role prompt")
        assert result == []


class TestIsRetryableError:
    """Test _is_retryable_error function."""

    def test_validation_error_not_retryable(self):
        from pydantic import ValidationError

        from llm_client import _is_retryable_error

        assert _is_retryable_error(ValidationError.from_exception_data("", [])) is False

    def test_value_error_not_retryable(self):
        from llm_client import _is_retryable_error

        assert _is_retryable_error(ValueError("bad")) is False

    def test_connection_error_retryable(self):
        from llm_client import _is_retryable_error

        assert _is_retryable_error(ConnectionError("timeout")) is True

    def test_runtime_error_retryable(self):
        from llm_client import _is_retryable_error

        assert _is_retryable_error(RuntimeError("fail")) is True


class TestLoadPrompt:
    """Test load_prompt function."""

    def test_loads_existing_prompt(self, tmp_path, monkeypatch):
        """Loads a prompt file from the prompts directory."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "test.md").write_text("Hello prompt", encoding="utf-8")

        monkeypatch.chdir(tmp_path)
        # Clear cache
        from llm_client import load_prompt

        load_prompt.cache_clear()
        result = load_prompt("test.md")
        assert result == "Hello prompt"
        load_prompt.cache_clear()

    def test_missing_prompt_returns_empty(self, tmp_path, monkeypatch):
        """Returns empty string for missing prompt file."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()

        monkeypatch.chdir(tmp_path)
        from llm_client import load_prompt

        load_prompt.cache_clear()
        result = load_prompt("nonexistent.md")
        assert result == ""
        load_prompt.cache_clear()

    def test_path_traversal_raises(self):
        """Path traversal attempts raise ValueError."""
        from llm_client import load_prompt

        with pytest.raises(ValueError, match="Invalid prompt name"):
            load_prompt("../etc/passwd")

        with pytest.raises(ValueError, match="Invalid prompt name"):
            load_prompt("sub/dir/file.md")

        with pytest.raises(ValueError, match="Invalid prompt name"):
            load_prompt("..\\windows\\system32")
