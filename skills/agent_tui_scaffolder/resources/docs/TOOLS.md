# Essential AI Tools Implementation Guide
**Rule: Use these pure, local-optimized tools. Avoid massive scraping suites.**

## 1. Web Search Providers
### DuckDuckGo (Free, No API Key)
*[Requires: `pip install ddgs`]*

**CRITICAL RULE: Thread Isolation for Blocking Network Tools**
Because agents operate via `asyncio` inside the Textual TUI event loop, calling synchronous blocking libraries (like `ddgs` or `httpx`) inline will either crash the event loop or silently return empty generators. You **MUST** define network tools as `async def` and securely offload the blocking logic to `asyncio.to_thread()`.

```python
import re
import asyncio
from agent_framework import tool

@tool(approval_mode="never_require")
async def web_search(query: str, max_results: int = 5, topic: str = "general") -> str:
    """Search the web for information on a given query."""
    def _do_search():
        from ddgs import DDGS
        
        def _sanitize_snippet(text: str) -> str:
            """Strip CSS, SVG, and HTML artifacts from search snippets."""
            text = re.sub(r'<svg[\s\S]*?</svg>', '', text, flags=re.IGNORECASE)
            text = re.sub(r'<style[\s\S]*?</style>', '', text, flags=re.IGNORECASE)
            text = re.sub(r'<[^>]+>', '', text)
            text = re.sub(r"(?:[\w-]+=(?:'[^']*'|\"[^\"]*\")[\s]*){3,}", '', text)
            text = re.sub(r'%3[CEce][^%\s]{10,}', '', text)
            return re.sub(r'\s+', ' ', text).strip()

        result_texts = []
        if topic == "news":
            search_results = DDGS().news(query, max_results=max_results)
            for result in search_results:
                snippet = _sanitize_snippet(result.get("body", ""))
                result_texts.append(f"## {result.get('title')}\n**URL:** {result.get('url')}\n**Snippet:** {snippet}\n")
        else:
            search_results = DDGS().text(query, max_results=max_results)
            for result in search_results:
                snippet = _sanitize_snippet(result.get("body", ""))
                result_texts.append(f"## {result.get('title')}\n**URL:** {result.get('href')}\n**Snippet:** {snippet}\n")
                
        return f"Found {len(result_texts)} result(s):\n\n" + "\n".join(result_texts)

    try:
        return await asyncio.to_thread(_do_search)
    except Exception as e:
        return f"Search failed: {e}"
```

### Tavily Search (Freemium, High Quality)
Ideal when deep, parsed answers are required. Tavily returns clean markdown summaries out-of-the-box, significantly reducing local LLM formatting burn.
*[Requires: `pip install httpx`]*

```python
import os
import httpx
from agent_framework import tool

@tool
def tavily_deep_search(query: str) -> str:
    """Use Tavily for summarized web searches."""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return "Tavily API key missing. Cannot perform search."
        
    payload = {
        "api_key": api_key, "query": query, "search_depth": "basic", 
        "include_answer": True, "max_results": 3
    }
    resp = httpx.post("https://api.tavily.com/search", json=payload, timeout=10)
    data = resp.json()
    return data.get("answer") or "\n".join([r['content'] async for r in data.get('results', [])])
```

## 2. Raw URL Fetching
**Rule: Do not return raw HTML to small LLMs.**
import httpx
from bs4 import BeautifulSoup
from agent_framework import tool

@tool
def fetch_url_content(url: str) -> str:
    """Extract human-readable text from a target URL."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
        resp = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
        soup = BeautifulSoup(resp.text, "html.parser")
        # Strip noisy elements
        for script in soup(["script", "style", "nav", "footer"]):
            script.extract()
        text = soup.get_text(separator='\n')
        # Cleanup blank lines
        lines = (line.strip() for line in text.splitlines())
        clean_text = '\n'.join(line for line in lines if line)
        return clean_text[:20000] # Hard cap to protect local context window!
    except Exception as e:
        return f"Failed to fetch content: {str(e)}"
```

## 3. Sandboxed Local Workspace

You should empower your agents to read and write files securely without risking pollution to the host's primary disk hierarchy. By default, deploy an ephemeral in-memory dictionary. If persistent data storage is actively requested, users can easily re-wire the dictionary to standard library `pathlib.Path` disk operations.

```python
import os
from typing import Dict
from agent_framework import tool

# By default, use an ephemeral in-memory dictionary to prevent disk pollution.
# For persistent disk execution, users should swap this for `pathlib` storage.
_IN_MEMORY_FS: Dict[str, str] = {}

def _get_safe_path(filename: str) -> str:
    """Normalizes the filename and aggressively strips directory traversal attempts."""
    clean_name = os.path.basename(filename)
    if not clean_name or clean_name != filename:
        return "" # Simplified sandboxing for memory
    return clean_name

@tool
def write_workspace_file(filename: str, content: str) -> str:
    """Writes a text file into your execution memory workspace."""
    try:
        path = _get_safe_path(filename)
        if not path:
            return f"Error: Invalid filename '{filename}'."
        _IN_MEMORY_FS[path] = content
        return f"Success. Wrote {len(content)} characters to '{filename}'."
    except Exception as e:
        return f"Error: {e}"

@tool
def list_workspace_files() -> str:
    """List files in workspace, including line and character counts."""
    if not _IN_MEMORY_FS: return "Workspace empty."
    res = []
    for k, v in sorted(_IN_MEMORY_FS.items()):
        res.append(f"{k} (Lines: {len(v.splitlines())}, Chars: {len(v)})")
    return "\n".join(res)

@tool
def read_workspace_file(filename: str, start_line: int = 1, end_line: int = -1) -> str:
    """Reads a previously written text file. Use start_line and end_line bounds to read large files safely. Both bounds are 1-indexed."""
    try:
        path = _get_safe_path(filename)
        if not path or path not in _IN_MEMORY_FS:
            return f"Error: File '{filename}' does not exist."
            
        lines = _IN_MEMORY_FS[path].splitlines()
        total = len(lines)
        max_lines = 300 # You MUST set this via config quotas in production
        
        if end_line == -1: end_line = total
        start, end = max(1, start_line), min(total, end_line)
        
        if (end - start + 1) > max_lines:
            return f"Error: Requested {end - start + 1} lines, but quota restricts to {max_lines}. Use grep_workspace_file instead."
            
        chunk = "\n".join(lines[start - 1:end])
        return f"--- {filename} [Lines {start}-{end} of {total}] ---\n{chunk}"
    except Exception as e:
        return f"Error: {e}"

@tool
def grep_workspace_file(filename: str, pattern: str, context_lines: int = 2) -> str:
    """Search for a regex pattern within a file, returning matching lines with surrounding context."""
    try:
        path = _get_safe_path(filename)
        if not path or path not in _IN_MEMORY_FS: return f"Error: '{filename}' not found."
        
        import re
        lines = _IN_MEMORY_FS[path].splitlines()
        max_matches = 10 # You MUST set this via config quotas in production
        compiled = re.compile(pattern, re.IGNORECASE)
        matches = [i for i, line in enumerate(lines) if compiled.search(line)][:max_matches]
                    
        if not matches: return f"No matches found for '{pattern}'."
        
        out = []
        for match_idx in matches:
            start, end = max(0, match_idx - context_lines), min(len(lines), match_idx + context_lines + 1)
            out.append(f"--- Match near line {match_idx + 1} ---")
            for j in range(start, end):
                out.append(f"{j + 1:04d}{'> ' if j == match_idx else '  '}{lines[j]}")
                
        return "\n".join(out)
    except Exception as e: return f"Grep Error: {e}"
```

### Fetching URLs directly to the Filesystem

To prevent the LLM's context window from exploding with raw webpage text, provide a combined tool that scrapes a website and pipes it *directly* into the unified filesystem.

```python
import httpx
from bs4 import BeautifulSoup

@tool
def fetch_url_to_workspace(url: str, filename: str) -> str:
    """Extract human-readable text from a target URL and save it to the in-memory workspace."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
        resp = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
        soup = BeautifulSoup(resp.text, "html.parser")
        for script in soup(["script", "style", "nav", "footer"]):
            script.extract()
            
        clean_text = soup.get_text(separator='\n')
        
        path = _get_safe_path(filename)
        if not path:
            return f"Error: Invalid filename '{filename}'."
        _IN_MEMORY_FS[path] = clean_text[:30000] # Protect memory size
        return f"Successfully fetched URL and saved content to '{filename}' in memory."
    except Exception as e:
        return f"Failed to fetch content: {str(e)}"
```

## 4. The `think_tool` Strategy
**Rule: Use for non-reasoning models or when native `<think>` capabilities are disabled to save compute.**
It forces the model to synthesize observations before acting.
from agent_framework import tool

@tool(approval_mode="never_require")
def think_tool(reflection: str) -> str:
    """Use this to record deliberate thinking / reasoning about the current situation and potentially next steps in a concise way.
    
    [AGENT INSTRUCTION: Always tailor this tool's docstring to the specific domain you are coding for to ensure the LLM knows what to "think" about.]
    """
    return f"Reflection recorded: {reflection}"
```

## 5. Non-Text Document Processing
**Rule: Always use `markitdown` or `liteparse` to convert downloaded webpages, raw HTML, PDFs, and rich documents into markdown formats before passing them to the LLM context.**

When agents need to process rich documents (PDFs, PPTX, DOCX, Receipts, Images) or complex visual layouts, rely on established parsing libraries rather than attempting to hand-roll PyPDF2/Tesseract extraction logic or returning raw HTML strings.

### MarkItDown (General Purpose Conversion)
Microsoft's `markitdown` is an excellent, stateless Python utility that converts HTML, PDFs, DOCX, PPTX, and XLSX directly to LLM-friendly markdown formatting.
*[Requires: `pip install markitdown[all]`]*

**Example from `local-research`:**
```python
from markitdown import MarkItDown
from agent_framework import tool

# Shared instance (stateless, computationally safe to reuse)
_markitdown = MarkItDown()

@tool
def fetch_and_convert_document(url_or_path: str) -> str:
    """Fetch and convert an rich document to markdown format."""
    try:
        result = _markitdown.convert(url_or_path)
        if result and result.text_content and result.text_content.strip():
            # Cap the response to protect the local LLM context window!
            return result.text_content[:30000] 
        return "Warning: Document was empty or could not be parsed."
    except Exception as e:
        return f"Conversion failed: {e}"
```

### LlamaIndex Liteparse (Local OCR / High Fidelity PDFs)
While `markitdown` handles structured text, scanned PDFs and receipts require robust OCR. For this, utilize LlamaIndex's Node.js-based `liteparse` CLI. It leverages high-fidelity models locally without cloud subscriptions.
*[Requires: Node.js and globally running `npm install -g @llamaindex/liteparse`]*

**Example from `tax-assistant`:**
```python
import os
import subprocess
import threading
from agent_framework import tool

_INSTALL_LOCK = threading.Lock()
_IS_INSTALLED = False

def ensure_liteparse():
    """Forces NPX to resolve and cache the library quietly."""
    global _IS_INSTALLED
    with _INSTALL_LOCK:
        if not _IS_INSTALLED:
            subprocess.run(["npx", "--yes", "@llamaindex/liteparse", "--help"], capture_output=True, check=False)
            _IS_INSTALLED = True

@tool
def robust_ocr_parse(file_path: str) -> str:
    """Extract complex text/receipt data from a PDF or image via Liteparse OCR."""
    plain_text_extensions = {".csv", ".txt", ".json", ".md", ".tsv"}
    ext = os.path.splitext(file_path)[1].lower()
    
    # Fast path: skip OCR for raw text
    if ext in plain_text_extensions:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    ensure_liteparse()
    cmd = ["npx", "--yes", "@llamaindex/liteparse", "parse", str(file_path), "--format", "text"]
    try:
        # Offload intensive CLI execution locally
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout[:30000]
    except subprocess.CalledProcessError as e:
        return f"Failed to parse {file_path}. Error: {e.stderr}"
```
