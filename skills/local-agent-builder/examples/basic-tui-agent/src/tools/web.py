import httpx
import os
import re
import asyncio
from bs4 import BeautifulSoup
from agent_framework import tool
from tools.core import with_quota
from tools.fs import _get_safe_path, _get_workspace_type, _get_workspace_dir, _IN_MEMORY_FS

@tool
@with_quota
async def fetch_url_to_workspace(url: str, filename: str, convert_to_md: bool = True) -> str:
    """Fetch external web content and save it directly to the workspace. If convert_to_md is True, parses to Markdown."""
    def _fetch():
        if convert_to_md:
            try:
                from utils.parsers import convert_to_markdown
                md_content = convert_to_markdown(url)
                if md_content: return md_content
            except ImportError:
                pass
                
            # Fallback to standard HTTPX and BeautifulSoup
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
            resp = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
            soup = BeautifulSoup(resp.text, "html.parser")
            for script in soup(["script", "style", "nav", "footer"]): script.extract()
            return '\n'.join(line for line in (l.strip() for l in soup.get_text(separator='\n').splitlines()) if line)
        else:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
            resp = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
            return resp.content # Return raw bytes
        
    try:
        data = await asyncio.to_thread(_fetch)
        
        # Explicitly tag markdown files
        if convert_to_md and not filename.endswith('.md'):
            filename += '.md'
            
        path = _get_safe_path(filename)
        if not path: return f"Error: Invalid filename '{filename}'."
        
        if isinstance(data, str):
            chunk = data[:100000] # Allow larger sizes for markdown text
            mode = "w"
            encoding = "utf-8"
        else:
            chunk = data[:5000000] # Cap raw binary at 5MB
            mode = "wb"
            encoding = None
        
        if _get_workspace_type() == "disk":
            os.makedirs(_get_workspace_dir(), exist_ok=True)
            if encoding:
                with open(path, mode, encoding=encoding) as f:
                    f.write(chunk)
            else:
                with open(path, mode) as f:
                    f.write(chunk)
            return f"Fetched URL successfully to '{filename}' on disk."
        else:
            _IN_MEMORY_FS[path] = chunk
            return f"Fetched URL successfully to '{filename}' in memory."
    except Exception as e: return f"Failed: {e}"

@tool(approval_mode="never_require")
@with_quota
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
