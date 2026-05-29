# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Deep Documentation

`.wiki/` holds full project documentation. Quick reference: `.wiki/ai-context.md`. Full docs start at `.wiki/README.md`. Covers graph structure, node details, prompt system, risks, and LLM call chains.

## Build & Development Commands

```bash
poetry install                      # Install dependencies
poetry run python cli.py --all      # Run full code review
poetry run python cli.py --diff origin/main  # Incremental review against branch
poetry run python cli.py --path src/ -o report.md  # Review specific path

# Testing
poetry run pytest                          # Run all tests
poetry run pytest tests/test_config.py     # Run single test file
poetry run pytest tests/test_graph.py::test_graph_runs -v  # Run single test

# Linting & Type Checking
poetry run ruff check .                    # Lint
poetry run ruff format --check .           # Format check
poetry run mypy .                          # Type check

# CI (Python 3.11/3.12/3.13): ruff check, ruff format check, mypy, pytest --cov-fail-under=80
```

## Architecture

Multi-agent code review system built on LangGraph. A single `StateGraph(SharedReviewState)` runs a fan-out/fan-in pattern:

```
coordinator → [sec_expert, arch_expert, perf_expert] (parallel) → reporter → END
```

**Key design points:**

- **No external tools/MCP** — expert nodes call `LLMClient.review_code()` directly
- **No memory/checkpoint** — state is ephemeral per `graph.invoke()` call
- **No conditional edges or router** — static DAG topology
- **State accumulation** — `raw_comments` uses `Annotated[List[AgentIssue], operator.add]` so parallel expert results merge automatically
- **Cost model:** LLM calls = files × 3 experts, peak parallelism = 15 (3 nodes × 5 threads each)
- **Provider support:** anthropic/openai/deepseek/glm via `LLM_PROVIDER` env var or `.scx-code-agent.yaml`
- **Prompt system:** `system_message = base.md + role_prompt`, LLM output parsed as JSON with `_repair_json()` fallback
- **Config priority:** file (`.scx-code-agent.yaml`) → env vars → defaults, supports `${VAR}` substitution
