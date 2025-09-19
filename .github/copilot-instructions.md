# Copilot Cleanup Rules
purpose: >
  Guide Copilot to systematically clean, refactor, and modernize the repository
  without inventing new features or altering business logic.

rules:
  - Only remove code if unused (functions, classes, methods, imports).
  - Refactor long methods (>50 lines) into smaller, reusable functions.
  - Extract repeated logic into shared utilities or modules.
  - Apply consistent naming and coding style (PEP8 for Python).
  - Never hallucinate new business logic or dependencies.
  - If unsure, output a TODO item instead of changing logic.

todo_list:
  hygiene:
    - "[ ] Identify and remove unused functions/classes/methods"
    - "[ ] Remove dead imports and libraries not referenced"
    - "[ ] Detect duplicate code blocks for extraction"
  refactoring:
    - "[ ] Refactor overly large classes into smaller, focused units"
    - "[ ] Break long methods into reusable functions"
    - "[ ] Ensure each class/function has a single responsibility"
  utilities:
    - "[ ] Extract repeated logic into utils/ or lib/"
    - "[ ] Centralize constants (magic numbers, strings)"
    - "[ ] Standardize error handling and logging"
  documentation:
    - "[ ] Add docstrings for public methods and complex logic"
    - "[ ] Improve inline comments where logic is non-obvious"
    - "[ ] Update README and CONTRIBUTING if refactors affect usage"
  consistency:
    - "[ ] Apply consistent formatting with black/eslint/prettier"
    - "[ ] Standardize naming across modules and files"
    - "[ ] Remove legacy or conflicting style patterns"
  testing:
    - "[ ] Add/expand unit tests for refactored code"
    - "[ ] Ensure regression tests cover critical paths"
  structure:
    - "[ ] Group related modules logically"
    - "[ ] Relocate orphan files into appropriate directories"
    - "[ ] Ensure consistent folder naming (src/, tests/, docs/)"
  stretch:
    - "[ ] Introduce type hints where missing (Python)"
    - "[ ] Add static analysis (mypy, pylint, SonarQube)"
    - "[ ] Setup CI checks for linting, testing, coverage"
    - "[ ] Audit dependencies (remove unused, upgrade old ones)"
