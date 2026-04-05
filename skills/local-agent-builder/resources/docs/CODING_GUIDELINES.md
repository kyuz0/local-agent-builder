# LLM-Friendly Coding Guidelines

When extending or maintaining applications built using this scaffold, you must adhere strictly to these rules. This codebase is designed to be written, read, and maintained natively by Local LLMs operating context windows. Large, bloated files, deep hierarchies, and excessive comments degrade token efficiency and cause "context rot".

## 1. Directory Structure: Flat over Nested
Do not create complex topological trees. Avoid nesting submodules deeply.
- **BAD**: `src/tools/web/scrapers/beautifulsoup_fetcher.py`
- **GOOD**: `src/tools/web.py`

Grouping functions into broad, logical domain containers (`fs.py`, `todos.py`, `web.py`) placed inside a flat folder limits the navigation overhead required to find a tool.

## 2. Minimal Comments (Code Speaks Form)
Do not clutter the codebase with meaningless inline commentary. Every comment burns tokens during context ingestion.
- **BAD**: `# Now we loop over every line in lines`
- **GOOD**: *No comment.*

You **are required** to document tool functions via structured python `docstrings`. This is because the Agent framework reads the function docstrings and explicitly pipes them to the LLM orchestrator. 
If a hack or workaround is necessary, use a comment ONLY to explain *why* it was done, never *what* it is doing.

## 3. Strict Type Hinting
Every single function boundary must include robust Python type hints.
- Type hints allow an LLM reading an `__init__.py` file to instantly understand how an imported module API behaves without needing to read the entire underlying logic block.

## 4. Single-Namespace Forwarding 
When building a package (like `src/tools/`), you must ensure that all tools from all different modules are cleanly aggregated inside the `__init__.py`. 
- Consumers (like `main.py`) should NEVER import from submodules like `from tools.web import fetch_url_to_workspace`. 
- They should always import from the parent: `from tools import fetch_url_to_workspace`.

## 5. File Scoping & Single Responsibility
Keep highly related tools inside identical files to preserve conceptual context. However, do not let files exceed a reasonable complexity boundary. If you are adding a completely unrelated domain—such as tools to execute PostgreSQL queries—do not lazily bolt them inside `fs.py` just to save a file creation step. Make a new `src/tools/sql.py` file, and append it to `src/tools/__init__.py`.
