#!/usr/bin/env python3
"""
SiteVoice — section-by-section personal site editor for bleonardi.github.io

Walk through each QMD section, rewrite in your voice, get AI suggestions,
and search literature for academic sections.
"""

import json
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import subprocess
from PySide6.QtCore import QThread, Signal, Qt, QTimer
from PySide6.QtGui import QFont, QFontDatabase, QColor, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTreeWidget, QTreeWidgetItem, QTextEdit, QTextBrowser,
    QLabel, QPushButton, QProgressBar, QGroupBox, QDialog,
    QDialogButtonBox, QLineEdit, QComboBox, QListWidget, QListWidgetItem,
    QStatusBar, QSizePolicy, QFormLayout, QFileDialog, QToolBar,
)

# ── Paths ──────────────────────────────────────────────────────────────────
TOOLS_DIR = Path(__file__).parent
SITE_ROOT = TOOLS_DIR.parent
PROGRESS_FILE = TOOLS_DIR / "progress.json"
DRAFTS_DIR = TOOLS_DIR / "drafts"
SETTINGS_FILE = TOOLS_DIR / "settings.json"
BIB_FILE = TOOLS_DIR / "references.bib"

# ── Palette ────────────────────────────────────────────────────────────────
BG       = "#f8f6f1"
BG2      = "#f0ece4"
CARD     = "#ffffff"
TEXT     = "#2c2a25"
TEXT2    = "#5c5850"
MUTED    = "#8a857c"
BORDER   = "#e2ded6"
ACCENT   = "#7a5c2e"
ACCENT_H = "#634b24"

QSS = f"""
QWidget {{
    background: {BG};
    color: {TEXT};
    border: none;
    font-size: 13px;
}}
QMainWindow {{ background: {BG}; }}
QToolBar {{
    background: {BG2};
    border-bottom: 1px solid {BORDER};
    padding: 4px 8px;
    spacing: 6px;
}}
QTreeWidget {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px;
    outline: none;
}}
QTreeWidget::item {{
    padding: 4px 6px;
    border-radius: 4px;
    color: {TEXT2};
}}
QTreeWidget::item:selected {{
    background: rgba(26,122,109,0.10);
    color: {ACCENT};
}}
QTreeWidget::item:hover:!selected {{
    background: {BG2};
}}
QTextEdit, QTextBrowser {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 10px;
    selection-background-color: rgba(26,122,109,0.18);
}}
QTextEdit:focus {{ border-color: {ACCENT}; }}
QPushButton {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 5px;
    padding: 6px 14px;
    color: {TEXT};
    font-size: 12px;
}}
QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}
QPushButton:pressed {{ background: {BG2}; }}
QPushButton:disabled {{ color: {MUTED}; border-color: {BORDER}; }}
QPushButton[objectName="primary"] {{
    background: {TEXT}; color: white; border-color: {TEXT};
}}
QPushButton[objectName="primary"]:hover {{
    background: {ACCENT}; border-color: {ACCENT};
}}
QPushButton[objectName="accent"] {{
    background: {ACCENT}; color: white; border-color: {ACCENT};
}}
QPushButton[objectName="accent"]:hover {{
    background: {ACCENT_H}; border-color: {ACCENT_H};
}}
QPushButton[objectName="done"] {{
    background: #4a7a50; color: white; border-color: #3a6040;
}}
QGroupBox {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 8px;
    margin-top: 14px;
    padding: 8px 6px 6px 6px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
    color: {MUTED};
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
QProgressBar {{
    background: {BG2};
    border: none;
    border-radius: 3px;
    max-height: 6px;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}
QScrollBar:vertical {{
    background: transparent; width: 6px; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #c8c4bc; border-radius: 3px; min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: transparent; height: 6px; margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: #c8c4bc; border-radius: 3px; min-width: 20px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QListWidget {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 6px;
    outline: none;
}}
QListWidget::item {{ padding: 4px 8px; border-radius: 4px; }}
QListWidget::item:selected {{
    background: rgba(26,122,109,0.10); color: {ACCENT};
}}
QSplitter::handle:horizontal {{ background: {BORDER}; width: 1px; }}
QLineEdit {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 5px;
    padding: 5px 8px;
    color: {TEXT};
}}
QLineEdit:focus {{ border-color: {ACCENT}; }}
QComboBox {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 5px;
    padding: 4px 8px;
    color: {TEXT};
}}
QStatusBar {{
    background: {BG2};
    border-top: 1px solid {BORDER};
    color: {MUTED};
    font-size: 11px;
}}
QDialog {{ background: {BG}; }}
"""


# ── Data model ─────────────────────────────────────────────────────────────
@dataclass
class Section:
    id: str           # "research.qmd::the-sprawl-paradox"
    file: str         # "research.qmd"
    title: str        # "The Sprawl Paradox"
    content: str      # editable prose (no ### heading, no tags for cards)
    mode: str         # "personal" or "academic"
    tags: list = field(default_factory=list)
    heading_line: str = ""  # "### [Title](url)" for project cards, else ""
    file_text: str = ""     # exact text in the QMD that `content` maps to (for write-back)


# ── QMD Parser ─────────────────────────────────────────────────────────────
def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _strip_yaml(text: str) -> str:
    if text.startswith("---"):
        end = text.index("---", 3)
        return text[end + 3 :].lstrip()
    return text


def _extract_tags(block: str) -> list:
    m = re.search(r":::\s*\{\.tags\}(.*?):::", block, re.DOTALL)
    if not m:
        return []
    return re.findall(r"\[([^\]]+)\]\{\.tag\}", m.group(1))


def _parse_card_blocks(body: str, fname: str, default_mode: str) -> list:
    """Parse project-card div blocks and ## section headers from a QMD body."""
    sections = []

    # Collect cards: ::: {.project-card} ... :::
    card_re = re.compile(
        r"::: \{\.project-card\}(.*?)(?=^:::|\Z)", re.DOTALL | re.MULTILINE
    )
    # Find positions of ## headings too
    heading_re = re.compile(r"^(## .+)$", re.MULTILINE)

    # Track which parts are cards vs headings vs prose
    used_spans = []

    # First add a section for any ## headings found
    for m in heading_re.finditer(body):
        heading_text = m.group(1)[3:].strip()
        sections.append(
            (
                m.start(),
                Section(
                    id=f"{fname}::{_slug(heading_text)}-header",
                    file=fname,
                    title=f"Section Header: {heading_text}",
                    content=m.group(1),
                    mode=default_mode,
                ),
            )
        )
        used_spans.append((m.start(), m.end()))

    # Then add project cards
    for m in card_re.finditer(body):
        inner = m.group(1).strip()
        # Close the block at :::
        inner = re.sub(r"\s*:::\s*$", "", inner).strip()

        title_m = re.search(r"(###\s+.+)", inner)
        if title_m:
            heading_line = title_m.group(1).strip()
            raw_title = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", title_m.group(1)[3:])
            title = raw_title.strip()
            # prose = everything after the heading line, before the tags block
            after_heading = inner[title_m.end():].strip()
        else:
            heading_line = ""
            title = f"Project {len(sections) + 1}"
            after_heading = inner

        tags = _extract_tags(after_heading)
        # file_text = prose as it literally appears in the file (no heading, no tags)
        file_text = re.sub(r"::: \{\.tags\}.*?:::", "", after_heading, flags=re.DOTALL).strip()

        sections.append(
            (
                m.start(),
                Section(
                    id=f"{fname}::{_slug(title)}",
                    file=fname,
                    title=title,
                    content=file_text,   # prose only — what the user edits
                    mode=default_mode,
                    tags=tags,
                    heading_line=heading_line,
                    file_text=file_text,
                ),
            )
        )

    sections.sort(key=lambda x: x[0])
    return [s for _, s in sections]


def _parse_index(fname: str, body: str) -> list:
    sections = []
    # Grab everything from the heading to end of the column block
    bio_m = re.search(r"## Benedict Leonardi\s*\n(.*?)(?=^:::|\Z)", body, re.DOTALL | re.MULTILINE)
    if not bio_m:
        return sections
    bio_body = bio_m.group(1)

    # Split bio paragraphs from Recent Work list
    rw_m = re.search(r"\n---\s*\n### Recent Work\s*\n(.*)", bio_body, re.DOTALL)
    if rw_m:
        bio_prose = bio_body[: rw_m.start()].strip()
        sections.append(Section(
            id=f"{fname}::bio",
            file=fname,
            title="Bio / About",
            content=bio_prose,
            mode="personal",
            file_text=bio_prose,
        ))
        rw_prose = ("### Recent Work\n" + rw_m.group(1)).strip()
        sections.append(Section(
            id=f"{fname}::recent-work",
            file=fname,
            title="Recent Work",
            content=rw_prose,
            mode="personal",
            file_text=rw_prose,
        ))
    else:
        bio_prose = bio_body.strip()
        sections.append(Section(
            id=f"{fname}::bio",
            file=fname,
            title="Bio / About",
            content=bio_prose,
            mode="personal",
            file_text=bio_prose,
        ))
    return sections


def _parse_card_page(fname: str, body: str, mode: str) -> list:
    sections = []
    # Intro text before first ----
    intro_m = re.match(r"^(.*?)\n---\n", body, re.DOTALL)
    if intro_m:
        intro = intro_m.group(1).strip()
        if len(intro) > 30:
            sections.append(Section(
                id=f"{fname}::intro",
                file=fname,
                title="Intro / Overview",
                content=intro,
                mode=mode,
                file_text=intro,
            ))
        remainder = body[intro_m.end():]
    else:
        remainder = body
    sections.extend(_parse_card_blocks(remainder, fname, mode))
    return sections


def _parse_dissertation(fname: str, body: str) -> list:
    sections = []
    intro_m = re.match(r"^(.*?)\n---\n", body, re.DOTALL)
    if intro_m:
        intro = intro_m.group(1).strip()
        if intro:
            sections.append(Section(
                id=f"{fname}::intro",
                file=fname,
                title="Dissertation Overview",
                content=intro,
                mode="academic",
                file_text=intro,
            ))
        remainder = body[intro_m.end():]
    else:
        remainder = body

    # Split by ## headings
    parts = re.split(r"\n(## .+?\n)", remainder)
    current_title = None
    current_parts = []

    def flush():
        if current_title:
            content = "".join(current_parts).strip()
            if content:
                sections.append(Section(
                    id=f"{fname}::{_slug(current_title)}",
                    file=fname,
                    title=current_title,
                    content=content,
                    mode="academic",
                    file_text=content,
                ))

    for part in parts:
        if part.startswith("## "):
            flush()
            current_title = part[3:].strip()
            current_parts = []
        else:
            current_parts.append(part)
    flush()
    return sections


def parse_site(site_root: Path) -> list:
    specs = [
        ("index.qmd",        "personal", _parse_index),
        ("research.qmd",     "academic", None),
        ("projects.qmd",     "personal", None),
        ("dissertation.qmd", "academic", _parse_dissertation),
    ]
    sections = []
    for fname, mode, parser in specs:
        path = site_root / fname
        if not path.exists():
            continue
        body = _strip_yaml(path.read_text())
        raw = parser(fname, body) if parser else _parse_card_page(fname, body, mode)
        # drop bare section-header stubs (no real prose to rewrite)
        sections.extend(s for s in raw if not s.title.startswith("Section Header:"))
    return sections


# ── Progress / draft store ─────────────────────────────────────────────────
class ProgressStore:
    def __init__(self):
        DRAFTS_DIR.mkdir(exist_ok=True)
        self._data: dict = {}
        if PROGRESS_FILE.exists():
            try:
                self._data = json.loads(PROGRESS_FILE.read_text())
            except Exception:
                pass

    def is_done(self, sid: str) -> bool:
        return self._data.get(sid, {}).get("done", False)

    def mark_done(self, sid: str, done: bool = True):
        self._data.setdefault(sid, {})["done"] = done
        self._save()

    def get_draft(self, sid: str) -> str:
        p = DRAFTS_DIR / f"{sid.replace('::', '__')}.md"
        return p.read_text() if p.exists() else ""

    def save_draft(self, sid: str, text: str):
        p = DRAFTS_DIR / f"{sid.replace('::', '__')}.md"
        p.write_text(text)

    def stats(self, sections: list) -> tuple:
        done = sum(1 for s in sections if self.is_done(s.id))
        return done, len(sections)

    def _save(self):
        PROGRESS_FILE.write_text(json.dumps(self._data, indent=2))


# ── Settings ───────────────────────────────────────────────────────────────
class Settings:
    _defaults = {
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
        "api_key": "",
        "bib_path": str(BIB_FILE),
    }

    def __init__(self):
        self._data = dict(self._defaults)
        if SETTINGS_FILE.exists():
            try:
                self._data.update(json.loads(SETTINGS_FILE.read_text()))
            except Exception:
                pass

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value):
        self._data[key] = value
        SETTINGS_FILE.write_text(json.dumps(self._data, indent=2))


# ── AI worker ──────────────────────────────────────────────────────────────
VOICE_SYSTEM = (
    "You are helping the user rewrite their personal academic website. "
    "The user's writing voice is: direct and confident without being boastful; "
    "intellectually serious with occasional dry wit; interdisciplinary — "
    "comfortable moving between empirical methods and philosophical/historical argument; "
    "uses precise technical language but plain English where it works; "
    "first-person but not confessional; names the organizing question explicitly "
    "before answering it. Avoids passive voice, hedging phrases, and generic "
    "academic phrasing. Medium-length sentences, compact purposeful paragraphs. "
    "Never sounds like AI-generated prose."
)


class AIWorker(QThread):
    result_ready = Signal(str)
    error = Signal(str)

    def __init__(self, prompt: str, settings: Settings):
        super().__init__()
        self.prompt = prompt
        self.settings = settings

    def run(self):
        try:
            key = self.settings.get("api_key", "")
            if not key:
                self.error.emit("No API key set. Open Settings to add one.")
                return
            provider = self.settings.get("provider", "anthropic")
            if provider == "anthropic":
                result = self._anthropic(key)
            else:
                result = self._openai(key)
            self.result_ready.emit(result)
        except Exception as e:
            self.error.emit(str(e))

    def _anthropic(self, key: str) -> str:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model=self.settings.get("model", "claude-sonnet-4-6"),
            max_tokens=2048,
            system=VOICE_SYSTEM,
            messages=[{"role": "user", "content": self.prompt}],
        )
        return msg.content[0].text

    def _openai(self, key: str) -> str:
        import openai
        client = openai.OpenAI(api_key=key)
        resp = client.chat.completions.create(
            model=self.settings.get("model", "gpt-4o"),
            max_tokens=2048,
            messages=[
                {"role": "system", "content": VOICE_SYSTEM},
                {"role": "user", "content": self.prompt},
            ],
        )
        return resp.choices[0].message.content


# ── Literature search worker ───────────────────────────────────────────────
@dataclass
class Paper:
    title: str
    authors: str
    year: int
    abstract: str
    doi: str
    url: str

    def bibtex_key(self) -> str:
        last = self.authors.split(",")[0].split()[-1].lower() if self.authors else "unknown"
        return re.sub(r"\W+", "", last) + str(self.year)

    def to_bibtex(self) -> str:
        key = self.bibtex_key()
        lines = [f"@article{{{key},"]
        lines.append(f"  title = {{{self.title}}},")
        lines.append(f"  author = {{{self.authors}}},")
        if self.year:
            lines.append(f"  year = {{{self.year}}},")
        if self.doi:
            lines.append(f"  doi = {{{self.doi}}},")
        if self.url:
            lines.append(f"  url = {{{self.url}}},")
        lines.append("}")
        return "\n".join(lines)


class LitSearchWorker(QThread):
    results_ready = Signal(list)
    error = Signal(str)

    def __init__(self, query: str):
        super().__init__()
        self.query = query

    def run(self):
        try:
            papers = self._search(self.query)
            self.results_ready.emit(papers)
        except Exception as e:
            self.error.emit(str(e))

    def _search(self, query: str) -> list:
        enc = urllib.parse.quote(query)
        url = (
            f"https://api.semanticscholar.org/graph/v1/paper/search"
            f"?query={enc}&limit=10"
            f"&fields=title,authors,year,abstract,externalIds,url"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "SiteVoice/1.0"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read())
        papers = []
        for item in data.get("data", []):
            authors = ", ".join(a["name"] for a in item.get("authors", [])[:4])
            doi = (item.get("externalIds") or {}).get("DOI", "")
            papers.append(Paper(
                title=item.get("title", ""),
                authors=authors,
                year=item.get("year") or 0,
                abstract=(item.get("abstract") or "")[:300],
                doi=doi,
                url=item.get("url", ""),
            ))
        return papers


# ── Git push worker ───────────────────────────────────────────────────────
class GitPushWorker(QThread):
    done = Signal(str)
    error = Signal(str)
    progress = Signal(str)

    def __init__(self, repo: Path):
        super().__init__()
        self.repo = repo

    def run(self):
        try:
            cwd = str(self.repo)
            env = {**__import__("os").environ, "PATH": "/usr/local/bin:/opt/homebrew/bin:" + __import__("os").environ.get("PATH", "")}

            self.progress.emit("Rendering site…")
            r = subprocess.run(
                ["quarto", "render"], cwd=cwd, capture_output=True, text=True, env=env
            )
            if r.returncode != 0:
                self.error.emit("quarto render failed: " + (r.stderr or r.stdout).strip()[-300:])
                return

            self.progress.emit("Staging files…")
            r = subprocess.run(
                ["git", "add", "-u"], cwd=cwd, capture_output=True, text=True
            )
            if r.returncode != 0:
                self.error.emit(r.stderr.strip())
                return

            # Check if there's anything to commit
            r = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=cwd)
            if r.returncode == 0:
                self.error.emit("Nothing to commit — write your changes to file first.")
                return

            self.progress.emit("Committing…")
            r = subprocess.run(
                ["git", "commit", "-m", "Site voice rewrite via SiteVoice"],
                cwd=cwd, capture_output=True, text=True
            )
            if r.returncode != 0:
                self.error.emit(r.stderr.strip())
                return

            self.progress.emit("Pushing to GitHub…")
            r = subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=cwd, capture_output=True, text=True
            )
            if r.returncode != 0:
                self.error.emit(r.stderr.strip())
                return

            self.done.emit("Pushed to GitHub — site will update in ~30 seconds ✓")
        except Exception as e:
            self.error.emit(str(e))


# ── Settings dialog ────────────────────────────────────────────────────────
class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Settings")
        self.setMinimumWidth(430)

        layout = QFormLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        self.provider = QComboBox()
        self.provider.addItems(["anthropic", "openai"])
        self.provider.setCurrentText(settings.get("provider", "anthropic"))
        self.provider.currentTextChanged.connect(self._refresh_models)
        layout.addRow("Provider:", self.provider)

        self.model = QComboBox()
        layout.addRow("Model:", self.model)
        self._refresh_models(self.provider.currentText())
        self.model.setCurrentText(settings.get("model", "claude-sonnet-4-6"))

        self.api_key = QLineEdit(settings.get("api_key", ""))
        self.api_key.setEchoMode(QLineEdit.Password)
        self.api_key.setPlaceholderText("sk-ant-... or sk-...")
        layout.addRow("API Key:", self.api_key)

        bib_row = QHBoxLayout()
        self.bib_path = QLineEdit(settings.get("bib_path", str(BIB_FILE)))
        bib_btn = QPushButton("Browse")
        bib_btn.setFixedWidth(70)
        bib_btn.clicked.connect(self._browse_bib)
        bib_row.addWidget(self.bib_path)
        bib_row.addWidget(bib_btn)
        layout.addRow(".bib file:", bib_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _refresh_models(self, provider: str):
        self.model.clear()
        if provider == "anthropic":
            self.model.addItems([
                "claude-sonnet-4-6",
                "claude-opus-4-8",
                "claude-haiku-4-5-20251001",
            ])
        else:
            self.model.addItems(["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"])

    def _browse_bib(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "BibTeX file", str(BIB_FILE), "BibTeX (*.bib)"
        )
        if path:
            self.bib_path.setText(path)

    def _save(self):
        self.settings.set("provider", self.provider.currentText())
        self.settings.set("model", self.model.currentText())
        self.settings.set("api_key", self.api_key.text().strip())
        self.settings.set("bib_path", self.bib_path.text().strip())
        self.accept()


# ── Main window ────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = Settings()
        self.progress = ProgressStore()
        self.sections: list[Section] = parse_site(SITE_ROOT)
        self.current_idx = 0
        self._ai_worker: Optional[AIWorker] = None
        self._lit_worker: Optional[LitSearchWorker] = None
        self._papers: list[Paper] = []
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._flush_draft)

        self.setWindowTitle("SiteVoice")
        self.setMinimumSize(1200, 760)

        self._load_fonts()
        self._build_ui()
        self.setStyleSheet(QSS)

        if self.sections:
            self._load_section(0)

    # ── Fonts ──────────────────────────────────────────────────────────────
    def _load_fonts(self):
        for font_dir in [TOOLS_DIR / "assets" / "fonts", SITE_ROOT / "assets" / "fonts"]:
            if font_dir.exists():
                for f in font_dir.glob("*.ttf"):
                    QFontDatabase.addApplicationFont(str(f))
                break
        QApplication.instance().setFont(QFont("DM Sans", 13))

    # ── UI construction ────────────────────────────────────────────────────
    def _build_ui(self):
        self._build_toolbar()

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 6)
        root.setSpacing(8)

        outer = QSplitter(Qt.Horizontal)
        outer.setHandleWidth(1)
        root.addWidget(outer)

        outer.addWidget(self._build_tree_panel())
        outer.addWidget(self._build_center_panel())
        outer.addWidget(self._build_ai_panel())
        outer.setSizes([200, 720, 280])

        root.addWidget(self._build_bottom_bar())

        self.setStatusBar(QStatusBar())

    def _build_toolbar(self):
        bar = QToolBar()
        bar.setMovable(False)
        self.addToolBar(bar)

        title = QLabel("SiteVoice")
        title.setStyleSheet(
            f"font-family: 'Source Serif 4', serif; font-size: 15px; "
            f"font-weight: 600; color: {TEXT}; margin-right: 20px; background: transparent;"
        )
        bar.addWidget(title)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        bar.addWidget(spacer)

        settings_btn = QPushButton("Settings")
        settings_btn.setFixedHeight(26)
        settings_btn.clicked.connect(self._open_settings)
        bar.addWidget(settings_btn)

    def _build_tree_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 6, 0)
        layout.setSpacing(5)

        cap = QLabel("Sections")
        cap.setStyleSheet(
            f"font-size: 10px; font-weight: 600; color: {MUTED}; "
            f"text-transform: uppercase; letter-spacing: 0.5px; background: transparent;"
        )
        layout.addWidget(cap)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(12)
        self.tree.currentItemChanged.connect(self._on_tree_change)
        layout.addWidget(self.tree)
        self._populate_tree()

        return panel

    def _populate_tree(self):
        self.tree.blockSignals(True)
        self.tree.clear()
        file_nodes: dict = {}
        file_labels = {
            "index.qmd": "Home",
            "research.qmd": "Research",
            "projects.qmd": "Projects",
            "dissertation.qmd": "Dissertation",
        }

        for i, s in enumerate(self.sections):
            if s.file not in file_nodes:
                node = QTreeWidgetItem([file_labels.get(s.file, s.file)])
                node.setData(0, Qt.UserRole, None)
                node.setForeground(0, QColor(MUTED))
                f = node.font(0)
                f.setPointSize(11)
                f.setBold(True)
                node.setFont(0, f)
                self.tree.addTopLevelItem(node)
                file_nodes[s.file] = node

            done = self.progress.is_done(s.id)
            label = f"✓ {s.title}" if done else s.title
            child = QTreeWidgetItem([label])
            child.setData(0, Qt.UserRole, i)
            if done:
                child.setForeground(0, QColor(ACCENT))
            file_nodes[s.file].addChild(child)

        self.tree.expandAll()
        self.tree.blockSignals(False)

    def _build_center_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Header row
        hdr = QHBoxLayout()
        self.section_title_lbl = QLabel("")
        self.section_title_lbl.setStyleSheet(
            f"font-family: 'Source Serif 4', serif; font-size: 16px; "
            f"font-weight: 600; color: {TEXT}; background: transparent;"
        )
        hdr.addWidget(self.section_title_lbl)
        hdr.addStretch()
        self.mode_lbl = QLabel("")
        self.mode_lbl.setStyleSheet(f"color: {MUTED}; font-size: 11px; background: transparent;")
        hdr.addWidget(self.mode_lbl)
        layout.addLayout(hdr)

        # Side-by-side text areas
        split = QSplitter(Qt.Horizontal)
        split.setHandleWidth(1)

        orig_box = QGroupBox("Original")
        ol = QVBoxLayout(orig_box)
        ol.setContentsMargins(4, 8, 4, 4)
        self.original_view = QTextBrowser()
        self.original_view.setReadOnly(True)
        ol.addWidget(self.original_view)

        rewrite_box = QGroupBox("Your Rewrite")
        rl = QVBoxLayout(rewrite_box)
        rl.setContentsMargins(4, 8, 4, 4)
        rl.setSpacing(4)

        # Shows the ### heading for project cards (preserved, not editable)
        self.heading_lbl = QLabel("")
        self.heading_lbl.setStyleSheet(
            f"font-family: 'DM Sans', sans-serif; font-size: 12px; font-weight: 600; "
            f"color: {MUTED}; background: {BG2}; border: 1px solid {BORDER}; "
            f"border-radius: 4px; padding: 4px 8px;"
        )
        self.heading_lbl.setWordWrap(True)
        self.heading_lbl.hide()
        rl.addWidget(self.heading_lbl)

        self.rewrite_edit = QTextEdit()
        self.rewrite_edit.setPlaceholderText(
            "Start typing your rewrite here, or click AI Suggest →"
        )
        self.rewrite_edit.textChanged.connect(self._on_rewrite_changed)
        rl.addWidget(self.rewrite_edit)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self.write_btn = QPushButton("⬆ Write to File")
        self.write_btn.setObjectName("primary")
        self.write_btn.setToolTip("Replace this section in the .qmd file right now")
        self.write_btn.clicked.connect(self._write_to_file)
        btn_row.addWidget(self.write_btn)
        self.push_btn = QPushButton("↑ Push to GitHub")
        self.push_btn.setToolTip("Commit changed files and push to origin/main")
        self.push_btn.clicked.connect(self._push_to_github)
        btn_row.addWidget(self.push_btn)
        rl.addLayout(btn_row)

        split.addWidget(orig_box)
        split.addWidget(rewrite_box)
        split.setSizes([1, 1])
        layout.addWidget(split)

        return panel

    def _build_ai_panel(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(276)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 0, 0, 0)
        layout.setSpacing(8)

        cap = QLabel("AI Assistant")
        cap.setStyleSheet(
            f"font-size: 10px; font-weight: 600; color: {MUTED}; "
            f"text-transform: uppercase; letter-spacing: 0.5px; background: transparent;"
        )
        layout.addWidget(cap)

        self.suggest_btn = QPushButton("Suggest Rewrite")
        self.suggest_btn.setObjectName("accent")
        self.suggest_btn.clicked.connect(self._ai_suggest)
        layout.addWidget(self.suggest_btn)

        self.tone_btn = QPushButton("Analyze Tone")
        self.tone_btn.clicked.connect(self._ai_analyze_tone)
        layout.addWidget(self.tone_btn)

        ai_box = QGroupBox("Suggestion")
        al = QVBoxLayout(ai_box)
        al.setContentsMargins(4, 8, 4, 4)
        al.setSpacing(5)
        self.ai_output = QTextBrowser()
        self.ai_output.setMinimumHeight(140)
        al.addWidget(self.ai_output)
        copy_btn = QPushButton("Copy to Rewrite →")
        copy_btn.clicked.connect(self._copy_ai_to_rewrite)
        al.addWidget(copy_btn)
        layout.addWidget(ai_box)

        # Literature search (academic mode only)
        self.lit_box = QGroupBox("Literature Search")
        ll = QVBoxLayout(self.lit_box)
        ll.setContentsMargins(4, 8, 4, 4)
        ll.setSpacing(4)

        self.lit_query = QLineEdit()
        self.lit_query.setPlaceholderText("Search query…")
        self.lit_query.returnPressed.connect(self._search_lit)
        ll.addWidget(self.lit_query)

        self.lit_btn = QPushButton("Search Semantic Scholar")
        self.lit_btn.clicked.connect(self._search_lit)
        ll.addWidget(self.lit_btn)

        self.lit_list = QListWidget()
        self.lit_list.setMaximumHeight(130)
        self.lit_list.setToolTip("Double-click to add to .bib")
        self.lit_list.itemDoubleClicked.connect(self._add_item_to_bib)
        ll.addWidget(self.lit_list)

        self.lit_add_btn = QPushButton("Add Selected to .bib")
        self.lit_add_btn.clicked.connect(self._add_selected_to_bib)
        ll.addWidget(self.lit_add_btn)

        layout.addWidget(self.lit_box)
        layout.addStretch()

        return panel

    def _build_bottom_bar(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet(
            f"background: {BG2}; border: 1px solid {BORDER}; "
            f"border-radius: 6px; padding: 0px;"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(10)

        self.prev_btn = QPushButton("← Prev")
        self.prev_btn.setFixedWidth(80)
        self.prev_btn.clicked.connect(self._go_prev)
        layout.addWidget(self.prev_btn)

        self.counter_lbl = QLabel("")
        self.counter_lbl.setStyleSheet(
            f"color: {MUTED}; font-size: 11px; min-width: 120px; "
            f"background: transparent; text-align: center;"
        )
        self.counter_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.counter_lbl)

        self.prog_bar = QProgressBar()
        self.prog_bar.setFixedHeight(6)
        self.prog_bar.setTextVisible(False)
        layout.addWidget(self.prog_bar)

        self.done_btn = QPushButton("Mark Done ✓")
        self.done_btn.setFixedWidth(110)
        self.done_btn.clicked.connect(self._toggle_done)
        layout.addWidget(self.done_btn)

        self.next_btn = QPushButton("Next →")
        self.next_btn.setObjectName("primary")
        self.next_btn.setFixedWidth(80)
        self.next_btn.clicked.connect(self._go_next)
        layout.addWidget(self.next_btn)

        return bar

    # ── Section loading ────────────────────────────────────────────────────
    def _load_section(self, idx: int):
        if not (0 <= idx < len(self.sections)):
            return
        self.current_idx = idx
        s = self.sections[idx]

        self.section_title_lbl.setText(s.title)
        mode_str = "Academic" if s.mode == "academic" else "Personal"
        self.mode_lbl.setText(f"{mode_str}  ·  {s.file}")

        # Original: show heading + prose together for context
        orig_text = (s.heading_line + "\n\n" + s.content) if s.heading_line else s.content
        self.original_view.setPlainText(orig_text)

        # Heading label (read-only, preserved on write-back)
        if s.heading_line:
            # Strip markdown link syntax for display
            display = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s.heading_line)
            display = re.sub(r"^###\s*", "", display)
            self.heading_lbl.setText(display)
            self.heading_lbl.show()
        else:
            self.heading_lbl.hide()

        self.rewrite_edit.blockSignals(True)
        self.rewrite_edit.setPlainText(self.progress.get_draft(s.id))
        self.rewrite_edit.blockSignals(False)

        self.ai_output.clear()
        self.lit_box.setVisible(s.mode == "academic")
        if s.mode == "academic":
            self.lit_query.setText(s.title)

        is_done = self.progress.is_done(s.id)
        self.done_btn.setText("✓ Done" if is_done else "Mark Done ✓")
        self.done_btn.setObjectName("done" if is_done else "")
        self.done_btn.style().polish(self.done_btn)

        self._sync_tree_selection(idx)
        self._update_nav()

    def _sync_tree_selection(self, idx: int):
        self.tree.blockSignals(True)
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            for j in range(top.childCount()):
                child = top.child(j)
                if child.data(0, Qt.UserRole) == idx:
                    self.tree.setCurrentItem(child)
                    self.tree.blockSignals(False)
                    return
        self.tree.blockSignals(False)

    def _update_nav(self):
        done, total = self.progress.stats(self.sections)
        self.prog_bar.setMaximum(total)
        self.prog_bar.setValue(done)
        self.counter_lbl.setText(
            f"{self.current_idx + 1} / {total}  ·  {done} done"
        )
        self.prev_btn.setEnabled(self.current_idx > 0)
        self.next_btn.setEnabled(self.current_idx < len(self.sections) - 1)

    # ── Navigation ─────────────────────────────────────────────────────────
    def _go_prev(self):
        if self.current_idx > 0:
            self._load_section(self.current_idx - 1)

    def _go_next(self):
        if self.current_idx < len(self.sections) - 1:
            self._load_section(self.current_idx + 1)

    def _on_tree_change(self, current, _previous):
        if current is None:
            return
        idx = current.data(0, Qt.UserRole)
        if idx is not None and idx != self.current_idx:
            self._load_section(idx)

    def _toggle_done(self):
        s = self.sections[self.current_idx]
        self.progress.mark_done(s.id, not self.progress.is_done(s.id))
        self._populate_tree()
        self._load_section(self.current_idx)

    # ── Draft auto-save ────────────────────────────────────────────────────
    def _on_rewrite_changed(self):
        self._save_timer.start(1200)

    def _flush_draft(self):
        s = self.sections[self.current_idx]
        self.progress.save_draft(s.id, self.rewrite_edit.toPlainText())
        self.statusBar().showMessage("Draft saved", 1500)

    # ── AI ─────────────────────────────────────────────────────────────────
    def _ai_suggest(self):
        s = self.sections[self.current_idx]
        partial = self.rewrite_edit.toPlainText().strip()
        if partial:
            prompt = (
                f"Below is a section from my personal academic website, and a partial rewrite I started. "
                f"Continue and polish the rewrite, matching my voice exactly.\n\n"
                f"Section: {s.title}\n\nORIGINAL:\n{s.content}\n\n"
                f"MY PARTIAL REWRITE:\n{partial}\n\n"
                f"Return only the completed rewrite, no preamble."
            )
        else:
            prompt = (
                f"Rewrite the following section from my personal academic website in my own voice. "
                f"It should feel genuinely personal, not like AI-generated prose.\n\n"
                f"Section: {s.title}\nMode: {s.mode}\n\nORIGINAL:\n{s.content}\n\n"
                f"Return only the rewritten text."
            )
        self._run_ai(prompt)

    def _ai_analyze_tone(self):
        s = self.sections[self.current_idx]
        target = self.rewrite_edit.toPlainText().strip() or s.content
        prompt = (
            f"Analyze the tone of the following text in 4 bullet points. "
            f"Flag: hedging phrases, passive voice, generic academic phrasing, "
            f"anything that sounds AI-generated. Be specific.\n\nTEXT:\n{target}"
        )
        self._run_ai(prompt)

    def _run_ai(self, prompt: str):
        if self._ai_worker and self._ai_worker.isRunning():
            return
        self.suggest_btn.setEnabled(False)
        self.tone_btn.setEnabled(False)
        self.ai_output.setPlainText("Thinking…")

        self._ai_worker = AIWorker(prompt, self.settings)
        self._ai_worker.result_ready.connect(self._on_ai_result)
        self._ai_worker.error.connect(self._on_ai_error)
        self._ai_worker.finished.connect(self._on_ai_done)
        self._ai_worker.start()

    def _on_ai_result(self, text: str):
        self.ai_output.setPlainText(text)
        self.statusBar().showMessage("AI suggestion ready", 2000)

    def _on_ai_error(self, err: str):
        self.ai_output.setPlainText(f"Error: {err}")
        self.statusBar().showMessage("AI error", 2000)

    def _on_ai_done(self):
        self.suggest_btn.setEnabled(True)
        self.tone_btn.setEnabled(True)

    def _copy_ai_to_rewrite(self):
        text = self.ai_output.toPlainText()
        if text and text not in ("Thinking…",) and not text.startswith("Error:"):
            self.rewrite_edit.setPlainText(text)

    # ── Literature search ──────────────────────────────────────────────────
    def _search_lit(self):
        query = self.lit_query.text().strip()
        if not query:
            return
        self.lit_btn.setEnabled(False)
        self.lit_list.clear()
        self.lit_list.addItem("Searching Semantic Scholar…")
        self._papers = []

        self._lit_worker = LitSearchWorker(query)
        self._lit_worker.results_ready.connect(self._on_lit_results)
        self._lit_worker.error.connect(self._on_lit_error)
        self._lit_worker.finished.connect(lambda: self.lit_btn.setEnabled(True))
        self._lit_worker.start()

    def _on_lit_results(self, papers: list):
        self._papers = papers
        self.lit_list.clear()
        for p in papers:
            first_author = p.authors.split(",")[0].split()[-1] if p.authors else "?"
            et_al = " et al." if "," in p.authors else ""
            title_short = p.title[:48] + "…" if len(p.title) > 48 else p.title
            item = QListWidgetItem(f"{first_author}{et_al} ({p.year})  {title_short}")
            item.setToolTip(p.abstract or p.title)
            self.lit_list.addItem(item)
        self.statusBar().showMessage(f"Found {len(papers)} papers", 2000)

    def _on_lit_error(self, err: str):
        self.lit_list.clear()
        self.lit_list.addItem(f"Error: {err}")

    def _add_item_to_bib(self, item: QListWidgetItem):
        idx = self.lit_list.row(item)
        if 0 <= idx < len(self._papers):
            self._write_bib_entry(self._papers[idx])

    def _add_selected_to_bib(self):
        for item in self.lit_list.selectedItems():
            idx = self.lit_list.row(item)
            if 0 <= idx < len(self._papers):
                self._write_bib_entry(self._papers[idx])

    def _write_bib_entry(self, paper: Paper):
        bib_path = Path(self.settings.get("bib_path", str(BIB_FILE)))
        entry = paper.to_bibtex()
        key = paper.bibtex_key()
        existing = bib_path.read_text() if bib_path.exists() else ""
        if key in existing:
            self.statusBar().showMessage(f"Already in .bib: {key}", 2000)
            return
        with open(bib_path, "a") as f:
            f.write("\n" + entry + "\n")
        self.statusBar().showMessage(f"Added {key} to {bib_path.name}", 2000)

    # ── Write to file ──────────────────────────────────────────────────────
    def _write_to_file(self):
        s = self.sections[self.current_idx]
        new_prose = self.rewrite_edit.toPlainText().strip()
        if not new_prose:
            self.statusBar().showMessage("Nothing to write — rewrite is empty.", 2500)
            return
        if not s.file_text:
            self.statusBar().showMessage("This section has no write-back target set.", 2500)
            return

        path = SITE_ROOT / s.file
        raw = path.read_text()

        if s.file_text not in raw:
            self.statusBar().showMessage(
                "Could not find original text in file — it may have changed externally.", 3000
            )
            return

        new_raw = raw.replace(s.file_text, new_prose, 1)
        path.write_text(new_raw)

        # Update in-memory section so subsequent writes are anchored to the new text
        s.file_text = new_prose
        s.content = new_prose

        self.statusBar().showMessage(f"Written to {s.file} ✓", 3000)

    # ── Git push ───────────────────────────────────────────────────────────
    def _push_to_github(self):
        self.push_btn.setEnabled(False)
        self.push_btn.setText("Pushing…")

        worker = GitPushWorker(SITE_ROOT)
        worker.done.connect(self._on_push_done)
        worker.error.connect(self._on_push_error)
        worker.progress.connect(lambda msg: self.statusBar().showMessage(msg))
        # keep reference so it isn't GC'd
        self._git_worker = worker
        worker.start()

    def _on_push_done(self, msg: str):
        self.push_btn.setEnabled(True)
        self.push_btn.setText("↑ Push to GitHub")
        self.statusBar().showMessage(msg, 4000)

    def _on_push_error(self, err: str):
        self.push_btn.setEnabled(True)
        self.push_btn.setText("↑ Push to GitHub")
        self.statusBar().showMessage(f"Git error: {err}", 5000)

    # ── Settings ───────────────────────────────────────────────────────────
    def _open_settings(self):
        dlg = SettingsDialog(self.settings, self)
        dlg.exec()


# ── Entry point ────────────────────────────────────────────────────────────
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("SiteVoice")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
