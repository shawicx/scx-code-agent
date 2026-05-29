import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, List

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, ValidationError, field_validator
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from agent.state import AgentIssue
from config import Config, load_config

logger = logging.getLogger(__name__)


def _is_retryable_error(exception: BaseException) -> bool:
    """判断异常是否可重试（仅对网络/超时/API错误重试，不对 ValidationError 重试）"""
    # 不重试验证错误和逻辑错误
    if isinstance(exception, (ValidationError, ValueError)):
        return False
    # 重试网络、超时等临时性错误
    return True


class IssueModel(BaseModel):
    """单个问题模型"""

    file_path: str = Field(..., description="文件路径")
    line_number: int = Field(..., ge=1, description="行号")
    category: str = Field(..., description="问题类别")
    level: str = Field(..., description="严重级别")
    description: str = Field(..., description="问题描述")
    suggestion: str = Field(..., description="修复建议")

    @field_validator("level")
    @classmethod
    def level_must_be_valid(cls, v: str) -> str:
        valid_levels = ["Blocker", "Warning", "Info"]
        if v not in valid_levels:
            raise ValueError(f"Invalid level: {v}, must be one of {valid_levels}")
        return v


class IssuesResponse(BaseModel):
    """问题响应模型"""

    issues: List[IssueModel] = Field(default_factory=list)

    def to_agent_issues(self) -> List[dict]:
        return [issue.model_dump() for issue in self.issues]


class LLMClient:
    """LLM 客户端封装"""

    # 默认上下文行数（可配置）
    DEFAULT_CONTEXT_LINES = 3

    def __init__(self, config: Config | dict | None = None, context_lines: int | None = None):
        """初始化 LLM 客户端

        Args:
            config: LLM 配置对象或字典，如果不提供则从环境变量加载
            context_lines: diff 模式下提取的上下文行数

        Raises:
            ValueError: 当 api_key 为空时抛出异常
        """
        if config is None:
            config = load_config()

        # 如果是字典，转换为 Config 对象
        if isinstance(config, dict):
            from config import OutputConfig, ProviderConfig, ReviewConfig

            provider_data = config.get("provider", {})
            config = Config(
                provider=ProviderConfig(**provider_data),
                review=ReviewConfig(**config.get("review", {})),
                output=OutputConfig(**config.get("output", {})),
            )

        self.provider = config.provider.name
        self.model = config.provider.model
        self.api_key = config.provider.api_key
        self.base_url = config.provider.base_url
        self.context_lines = context_lines if context_lines is not None else config.review.context_lines

        # 验证 api_key
        if not self.api_key:
            raise ValueError(
                f"API key is required for provider '{self.provider}'. "
                f"Please set the 'api_key' in your config or environment variable."
            )

        self._init_chat_model()

    def _init_chat_model(self):
        """初始化 ChatModel"""
        # 设置超时时间：GLM 模型可能需要更长时间，使用 120 秒
        timeout = 120 if self.provider == "glm" else 60

        if self.provider == "anthropic":
            self.chat_model = ChatAnthropic(model=self.model, api_key=self.api_key, temperature=0, timeout=timeout)
        elif self.provider == "openai":
            self.chat_model = ChatOpenAI(
                model=self.model, api_key=self.api_key, base_url=self.base_url, temperature=0, timeout=timeout
            )
        elif self.provider == "deepseek":
            self.chat_model = ChatOpenAI(
                model=self.model,
                api_key=self.api_key,
                base_url=self.base_url or "https://api.deepseek.com",
                temperature=0,
                timeout=timeout,
            )
        elif self.provider == "glm":
            self.chat_model = ChatOpenAI(
                model=self.model,
                api_key=self.api_key,
                base_url=self.base_url or "https://open.bigmodel.cn/api/paas/v4/",
                temperature=0,
                timeout=timeout,
            )
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    def _prepare_code_content(self, content: str, diff_lines: List[int] | None = None) -> tuple[str, dict, dict]:
        """准备传递给 LLM 的代码内容

        Args:
            content: 完整文件内容
            diff_lines: 变更行号列表（diff 模式）

        Returns:
            (处理后的内容, 原始行号到LLM行号的映射字典, LLM行号到原始行号的映射字典)

        Note:
            - orig_to_llm: 原始行号(1-based) -> LLM可见的行号(1-based)
            - llm_to_orig: LLM可见的行号(1-based) -> 原始行号(1-based)
        """
        if diff_lines is None or not diff_lines:
            return content, {}, {}

        # diff 模式：提取 diff_lines ± context_lines 行上下文
        lines = content.split("\n")

        included_lines = set()
        for line_num in diff_lines:
            for i in range(max(0, line_num - self.context_lines - 1), min(len(lines), line_num + self.context_lines)):
                included_lines.add(i)

        result_lines = []
        # 原始行号(1-based) -> LLM行号(1-based)
        orig_to_llm = {}
        # LLM行号(1-based) -> 原始行号(1-based)
        llm_to_orig = {}

        llm_line_num = 1  # LLM 看到的行号从 1 开始
        for i, line in enumerate(lines):
            if i in included_lines:
                result_lines.append(line)
                # 原始行号（1-based）
                orig_line_num = i + 1
                # 记录映射关系
                orig_to_llm[orig_line_num] = llm_line_num
                llm_to_orig[llm_line_num] = orig_line_num
                llm_line_num += 1

        return "\n".join(result_lines), orig_to_llm, llm_to_orig

    def _extract_json(self, text: str) -> str | Any:
        """从文本中提取 JSON

        处理可能被 Markdown 代码块包裹或其他文本包裹的情况
        """
        text = text.strip()

        # 方法1: 查找第一个 `[` 和最后一个 `]` 之间的内容
        first_bracket = text.find("[")
        last_bracket = text.rfind("]")

        if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
            json_candidate = text[first_bracket : last_bracket + 1]
            # 验证是否是有效的 JSON
            try:
                json.loads(json_candidate)
                return json_candidate
            except json.JSONDecodeError:
                pass  # 继续尝试其他方法

        # 方法2: 处理 Markdown 代码块 ```json ... ```
        if "```" in text:
            # 找到所有代码块
            pattern = r"```(?:json)?\s*\n?([\s\S]*?)\n?```"
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                try:
                    json.loads(match.strip())
                    return match.strip()
                except json.JSONDecodeError:
                    continue

        # 方法3: 如果整个文本看起来像 JSON，直接使用
        try:
            json.loads(text)
            return text
        except json.JSONDecodeError:
            pass

        # 如果所有方法都失败，返回原始文本
        return text

    def _repair_json(self, text: str) -> str:
        """尝试修复常见的 JSON 错误

        Args:
            text: 可能损坏的 JSON 字符串

        Returns:
            修复后的 JSON 字符串
        """
        # 修复未闭合的字符串 - 移除未闭合的字符串及其后面的内容
        lines = text.split("\n")
        repaired_lines = []

        for line in lines:
            # 检查是否有未闭合的字符串
            quote_count = line.count('"')
            if quote_count % 2 != 0:  # 奇数个引号
                # 尝试修复：移除最后一个未闭合字符串的内容
                last_quote = line.rfind('"')
                if last_quote != -1:
                    # 找到这一行中最后一个逗号或括号
                    for i, char in enumerate(line[last_quote + 1 :], start=last_quote + 1):
                        if char in ",}]":
                            line = line[: last_quote + 1] + char
                            break
                        elif char not in " \t\n\r":
                            # 遇到其他字符，这行可能有问题
                            line = line[:last_quote] + '"'
                            break
            repaired_lines.append(line)

        return "\n".join(repaired_lines)

    def _parse_response(self, response: str) -> List[AgentIssue]:
        """解析 LLM 响应

        Args:
            response: LLM 返回的文本

        Returns:
            AgentIssue 列表，解析失败时返回空列表
        """
        # 首次尝试解析
        json_text = self._extract_json(response)

        try:
            data = json.loads(json_text)
        except json.JSONDecodeError as e:
            # 尝试修复 JSON
            logger.warning(f"Initial JSON parse failed: {e}, attempting repair...")
            json_text = self._repair_json(json_text)

            try:
                data = json.loads(json_text)
                logger.info("JSON repair successful")
            except json.JSONDecodeError as e2:
                logger.error(f"Failed to decode JSON even after repair: {e2}")
                logger.debug(f"Response was: {response[:800]}...")
                return []

        # 处理两种可能的返回格式
        if isinstance(data, list):
            issues_data = data
        elif isinstance(data, dict) and "issues" in data:
            issues_data = data["issues"]
        else:
            logger.debug("LLM returned unexpected format - not a list or dict with 'issues'")
            return []

        # Pydantic 验证
        try:
            response_model = IssuesResponse(issues=issues_data)
            return [
                {
                    "file_path": issue.file_path,
                    "line_number": issue.line_number,
                    "category": issue.category,
                    "level": issue.level,
                    "description": issue.description,
                    "suggestion": issue.suggestion,
                }
                for issue in response_model.issues
            ]
        except ValidationError as e:
            logger.error(f"LLM response failed Pydantic validation: {e}")
            logger.debug(f"Invalid data: {json_text[:500]}...")
            return []

    @staticmethod
    def _get_code_fence_language(file_path: str) -> str:
        """根据文件扩展名获取代码围栏语言标识

        Args:
            file_path: 文件路径

        Returns:
            代码围栏语言标识（如 'python', 'typescript'）
        """
        ext = Path(file_path).suffix.lower()

        # 常见文件扩展名映射
        language_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".jsx": "javascript",
            ".java": "java",
            ".go": "go",
            ".rs": "rust",
            ".c": "c",
            ".cpp": "cpp",
            ".cc": "cpp",
            ".cxx": "cpp",
            ".h": "c",
            ".hpp": "cpp",
            ".cs": "csharp",
            ".php": "php",
            ".rb": "ruby",
            ".swift": "swift",
            ".kt": "kotlin",
            ".scala": "scala",
            ".sh": "bash",
            ".bash": "bash",
            ".zsh": "zsh",
            ".fish": "fish",
            ".sql": "sql",
            ".html": "html",
            ".css": "css",
            ".scss": "scss",
            ".less": "less",
            ".json": "json",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".xml": "xml",
            ".md": "markdown",
            ".dockerfile": "dockerfile",
            ".Dockerfile": "dockerfile",
        }

        # 处理特殊文件名
        if Path(file_path).name.lower() in ("dockerfile", ".dockerignore"):
            return "dockerfile"

        return language_map.get(ext, "text")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
        retry=retry_if_exception(lambda e: _is_retryable_error(e)),
    )
    def review_code(
        self, file_path: str, content: str, role_prompt: str, base_prompt: str = "", diff_lines: List[int] | None = None
    ) -> List[AgentIssue]:
        """审查单个文件

        Args:
            file_path: 文件路径
            content: 文件内容
            role_prompt: 专家角色 prompt
            base_prompt: 基础提示词模板
            diff_lines: 变更行号列表（diff 模式）

        Returns:
            AgentIssue 列表
        """
        # 准备代码内容
        code_content, orig_to_llm, llm_to_orig = self._prepare_code_content(content, diff_lines)

        # 获取代码围栏语言
        lang = self._get_code_fence_language(file_path)

        # 构建 prompt
        system_message = base_prompt + "\n\n" + role_prompt

        user_message = f"""请审查以下代码文件：{file_path}

```{lang}
{code_content}
```"""

        if diff_lines:
            # 显示原始行号给 LLM
            focus_lines = sorted(diff_lines)
            user_message += f"\n\n重点关注以下行号附近的代码：{focus_lines}"

        try:
            messages = [SystemMessage(content=system_message), HumanMessage(content=user_message)]

            logger.debug(f"Invoking LLM for {file_path} with {len(content)} chars of content")
            response = self.chat_model.invoke(messages)
            result = self._parse_response(response.content)

            # 修正行号（diff 模式下需要映射回原始行号）
            # LLM 返回的行号是它看到的行号（1-based），需要映射回原始文件行号
            if diff_lines:
                for issue in result:
                    llm_line = issue.get("line_number", 0)
                    # 使用 llm_to_orig 映射将 LLM 行号转为原始行号
                    if llm_line in llm_to_orig:
                        issue["line_number"] = llm_to_orig[llm_line]
                    else:
                        # 如果 LLM 返回的行号不在映射中，保持原样（可能是错误）
                        logger.warning(
                            f"LLM returned line {llm_line} which is not in the extracted content, "
                            f"available lines: {sorted(llm_to_orig.keys())}"
                        )

            return result

        except Exception as e:
            logger.error(f"LLM call failed for {file_path}: {e}")
            return []


@lru_cache(maxsize=8)
def load_prompt(prompt_name: str) -> str:
    """加载 prompt 文件内容（带缓存）

    Args:
        prompt_name: prompt 文件名（如 'security.md'）

    Returns:
        prompt 文件内容
    """
    # 防止路径遍历攻击：只允许文件名，不允许路径分隔符
    if "/" in prompt_name or "\\" in prompt_name or ".." in prompt_name:
        raise ValueError(f"Invalid prompt name: {prompt_name}")

    prompt_path = Path("prompts") / prompt_name
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.warning(f"Prompt file not found: {prompt_path}")
        return ""
