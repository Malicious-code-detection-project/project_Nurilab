# AI_RULES.md - AI Code Generation Guidelines

This document defines the core architecture, coding standards, and project structure rules that all AI agents (Gemini, Cursor, Copilot, etc.) MUST follow when generating or modifying code in this repository.

---

## 1. Tech Stack & Toolchain

| Category | Tool & Guidelines |
| --- | --- |
| **Language** | Python 3.12+ (Use modern Python features, `from __future__ import annotations`) |
| **Package Manager** | `uv` (Manage dependencies via `pyproject.toml`) |
| **Linter & Formatter** | `ruff` (Always adhere to ruff formatting, do not violate existing rules) |
| **Testing** | `pytest` (Located in the `tests/` directory) |

---

## 2. Coding Conventions & Style

### 2.1. Type Hinting (Strict)

- **All** functions, methods, and classes must have complete and accurate type hints.
- Do not use `# type: ignore` or explicit type-casting unless absolutely unavoidable and explicitly requested by the human developer.
- Return types and parameter types are mandatory.

### 2.2. Data Models

- Use `dataclasses` with `@dataclass(slots=True)` instead of heavy external validation libraries (like Pydantic) for internal data structures (refer to `project_nurilab/schemas.py`).
- Keep serialization logic explicit (e.g., implement `to_dict()`).

### 2.3. Documentation

- Provide a **file-level docstring** at the top of every new Python file.
- Use simple, descriptive docstrings for all classes and public functions.
- Keep comments focused on the "Why", not the "What" (the code should be self-documenting).

### 2.4. OOP & Architecture

- Follow the established Separation of Concerns. For instance, in AST parsing, separate the analyzer logic from the AST Visitor logic (e.g., `PythonStaticAnalyzer` and `_PythonSignalVisitor`).
- When extending analyzers, inherit from the appropriate base interfaces and place them in `project_nurilab/analyzers/`.

---

## 3. Project Structure Rules

| Directory / File | Rule / Responsibility |
| --- | --- |
| `project_nurilab/` | Main application code. |
| `project_nurilab/schemas.py` | Add all new data models and type definitions here. |
| `project_nurilab/analyzers/` | Place new static analysis or AST-related logic here. |
| `project_nurilab/llm/` | Place logic related to LLM interactions and external API reviews here. |
| `tests/` | All new features or bug fixes must be accompanied by corresponding `pytest` files. Test files should prefix with `test_` (e.g., `test_pipeline.py`). |
| `data/` & `tests/fixtures/` | Store sample code and test inputs here. Do not clutter the root directory. |

---

## 4. Execution Directives for AI Agents

- **Do not guess imports**: Verify the location of a function/class before importing it.
- **Run Tests**: Whenever a change is made to the core logic, remind the user to run `pytest` or autonomously run `pytest` if the capability is available.
- **Linting**: After code generation, ensure the output complies with `ruff check .` and `ruff format .`.
- **Atomic Changes**: Keep changes surgical and focused on the user's immediate request. Do not arbitrarily "clean up" unrelated code unless instructed.
