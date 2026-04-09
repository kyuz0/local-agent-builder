# Essential AI Tools Implementation Guide
**Rule: The `basic-tui-agent` scaffold provides ready-to-use implementations for all standard agentic tasks. You MUST import them from the scaffold instead of re-writing them from scratch.**

## 1. Web Search & Raw URL Fetching
**Rule: Network requests must be isolated into async threads to prevent TUI blocking.**

Instead of writing scraping suites from scratch:
- **`web_search` (DuckDuckGo)**: Use the robust `ddgs` thread-isolated tool provided in `examples/basic-tui-agent/src/tools/web.py`.
- **`tavily_deep_search` (Summarizations)**: Implemented via `httpx` in `src/tools/web.py`.
- **`fetch_url_content`**: Uses `BeautifulSoup` to safely strip JS/CSS and returns clean text. Also found in `src/tools/web.py`.

*CRITICAL constraint:* Do not return massive HTML payloads (raw `<html>`, `<nav>`, `<style>`) back to the context window. 

## 2. Sandboxed Local Workspace
**Rule: Empower agents to read/write files securely via the built-in Sandbox wrapper.**

You do not need to implement filesystem tools manually. The scaffold includes fully functional file interaction tools that inherently respect quotas (Line chunks, Regex limits):
- `write_workspace_file`
- `list_workspace_files`
- `read_workspace_file` (Auto-enforces robust line-count chunking)
- `grep_workspace_file` (Regex powered context-search)

**Usage:** Import these directly from `examples/basic-tui-agent/src/tools/fs.py`.

*Session Isolation Pattern:* If an agent requires isolated subfolders for each workflow or session, the filesystem tools automatically support a `session_dir_ctx` ContextVar. Do not create new generic workspace tools; instead, uncomment the `session_dir_ctx` setup block at the top of `main.py`'s `run_agent` loop to securely auto-route all file operations into a timestamped subfolder.

*Note:* A special combination tool, `fetch_url_to_workspace`, scrapes websites directly to the filesystem to preserve the LLM's context window. Find this in `src/tools/web.py`.

## 3. Non-Text Document Processing
**Rule: Always use `markitdown` or `liteparse` to handle complex PDFs, Images, and rich formats (`.docx`).**

Do not manually parse binary files with PyPDF2 or Tesseract. Use the centralized parsing implementations found inside `examples/basic-tui-agent/src/utils/parsers.py`:
- **For Standard Documents:** The scaffold incorporates Microsoft's `markitdown` for structural conversion of files.
- **For Heavy OCR / Scanned Layouts:** The scaffold leverages `@llamaindex/liteparse` via a local NPX subprocess hook. Always deploy this path when visual parsing is strictly demanded.
