from textual.app import App, ComposeResult
from textual.widgets import Markdown

class MarkdownApp(App):
    def compose(self) -> ComposeResult:
        yield Markdown("> [!WARNING]\n> **AUTO_APPROVE IS ENABLED**.\n\n### Test")

if __name__ == "__main__":
    app = MarkdownApp()
    # just parse it
    pass
