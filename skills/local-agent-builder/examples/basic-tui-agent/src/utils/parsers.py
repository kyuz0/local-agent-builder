import subprocess
import shutil
import httpx
try:
    from markitdown import MarkItDown
    _markitdown_available = True
    _markitdown = MarkItDown()
except ImportError:
    import logging
    logging.warning("markitdown not installed. Markdown conversion will be limited.")
    _markitdown_available = False

def convert_to_markdown(url_or_filepath: str) -> str:
    """
    Attempts to fetch and convert a URL or raw file to markdown using markitdown.
    Returns None if markitdown is unavailable or fails, allowing graceful fallback.
    """
    if not _markitdown_available:
        return None
        
    try:
        # Pass the URL directly to markitdown
        result = _markitdown.convert(url_or_filepath)
        if result and result.text_content:
            return result.text_content
        return None
    except Exception as e:
        return None

def extract_advanced_pdf(filepath: str) -> str:
    """
    Utilizes Liteparse for layout comprehension of complex PDFs. 
    Requires system-level installation: `npm install -g @llamaindex/liteparse`.
    """
    if not shutil.which("liteparse"):
        raise EnvironmentError("liteparse is missing. Run: npm install -g @llamaindex/liteparse")

    result = subprocess.run(
        ["liteparse", filepath], 
        capture_output=True, 
        text=True,
        check=True
    )
    return result.stdout
