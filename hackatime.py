"""
hackatime.py — Send heartbeats to Hackatime from your custom IDE
----------------------------------------------------------------
Key finding: Hackatime's Rails server reads the `user_agent` string
from the JSON body of each heartbeat (not just the HTTP header) and
parses it to populate editor, operating_system, and machine columns.

The exact WakaTime CLI User-Agent format it expects:
  wakatime/v2.15.0 (linux-6.17.0-35-generic-unknown) go1.26.3 sublime/4200 sublime-wakatime/11.1.1

Requirements:
    pip install requests
"""

import os
import time
import threading
import requests
from requests import Session
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Language map
# ---------------------------------------------------------------------------
EXTENSION_LANGUAGES: dict[str, str] = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
    ".jsx": "JavaScript (JSX)", ".tsx": "TypeScript (TSX)",
    ".html": "HTML", ".css": "CSS", ".scss": "SCSS", ".sass": "Sass",
    ".json": "JSON", ".yaml": "YAML", ".yml": "YAML", ".toml": "TOML",
    ".md": "Markdown", ".txt": "Text",
    ".c": "C", ".h": "C", ".cpp": "C++", ".cc": "C++", ".hpp": "C++",
    ".cs": "C#", ".java": "Java", ".kt": "Kotlin", ".swift": "Swift",
    ".go": "Go", ".rs": "Rust", ".rb": "Ruby", ".php": "PHP",
    ".sh": "Bash", ".bash": "Bash", ".zsh": "Zsh", ".fish": "Fish",
    ".lua": "Lua", ".r": "R", ".dart": "Dart", ".ex": "Elixir",
    ".exs": "Elixir", ".elm": "Elm", ".hs": "Haskell", ".ml": "OCaml",
    ".sql": "SQL", ".tf": "Terraform", ".vue": "Vue",
    ".svelte": "Svelte", ".xml": "XML",
}

def _detect_language(filepath: str) -> str:
    ext = Path(filepath).suffix.lower()
    return EXTENSION_LANGUAGES.get(ext, "Unknown")


# ---------------------------------------------------------------------------
# Core client
# ---------------------------------------------------------------------------
class HackatimeClient:
    """
    Sends WakaTime-compatible heartbeats to Hackatime.

    The server reads `user_agent` from the JSON body to populate editor,
    OS, and machine — so we include it in every heartbeat payload.
    """

    HEARTBEAT_ENDPOINT = "/api/hackatime/v1/users/current/heartbeats.bulk"
    MAX_BATCH = 25

    def __init__(
        self,
        api_key: str,
        editor_name: str = "sublime",
        editor_version: str = "4200",
        plugin_name: str = "sublime-wakatime",
        plugin_version: str = "11.1.1",
        wakatime_version: str = "v2.15.0",
        os_string: str = "linux-6.17.0-35-generic-unknown",
        operating_system: str = "linux",
        language_runtime: str = "go1.26.3",
        machine: str = "rupnil-pc-virtual",
        base_url: str = "https://hackatime.hackclub.com",
        auto_flush_interval: int = 30,
        batch_size: int = 25,
    ):
        if not api_key:
            raise ValueError("api_key is required")

        self.api_key          = api_key
        self.base_url         = base_url.rstrip("/")
        self.batch_size       = min(batch_size, self.MAX_BATCH)
        self.operating_system = operating_system
        self.machine          = machine
        self.editor_name      = editor_name

        # Full User-Agent string — sent both as HTTP header AND as a field
        # inside each heartbeat's JSON body (that's how the server parses it)
        self.user_agent = (
            f"wakatime/{wakatime_version} ({os_string}) {language_runtime} "
            f"{editor_name}/{editor_version} {plugin_name}/{plugin_version}"
        )

        # Persistent session — headers applied to every request
        self._session = Session()
        self._session.headers.update({
            "Authorization":  f"Bearer {self.api_key}",
            "Content-Type":   "application/json",
            "User-Agent":     self.user_agent,
            "X-Machine-Name": self.machine,
        })

        self._queue: list[dict] = []
        self._lock  = threading.Lock()
        self._last_file: Optional[str] = None
        self._last_heartbeat_time: float = 0.0

        if auto_flush_interval > 0:
            self._start_flush_timer(auto_flush_interval)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def heartbeat(
        self,
        file: str,
        project:     Optional[str] = None,
        language:    Optional[str] = None,
        branch:      Optional[str] = None,
        is_write:    bool = False,
        category:    str  = "coding",
        lines:       Optional[int] = None,
        cursor_pos:  Optional[int] = None,
        line_number: Optional[int] = None,
    ) -> None:
        """Queue a single heartbeat (debounced 30 s for non-writes)."""
        now = time.time()

        if (
            not is_write
            and file == self._last_file
            and (now - self._last_heartbeat_time) < 30
        ):
            return

        self._last_file = file
        self._last_heartbeat_time = now

        beat: dict = {
            "entity":           file,
            "type":             "file",
            "time":             now,
            "is_write":         is_write,
            "category":         category,
            "language":         language or _detect_language(file),
            # -------------------------------------------------------
            # These three fields go in the JSON body.
            # The server reads `user_agent` from here and parses it
            # to extract editor name, OS, etc.
            # -------------------------------------------------------
            "user_agent":       self.user_agent,
            "machine":          self.machine,
            "operating_system": self.operating_system,
        }

        if project:                  beat["project"]  = project
        if branch:                   beat["branch"]   = branch
        if lines       is not None:  beat["lines"]    = lines
        if cursor_pos  is not None:  beat["cursorpos"] = cursor_pos
        if line_number is not None:  beat["lineno"]   = line_number

        with self._lock:
            self._queue.append(beat)
            should_flush = len(self._queue) >= self.batch_size

        if should_flush:
            self.flush()

    def heartbeat_bulk(self, heartbeats: list[dict]) -> None:
        with self._lock:
            self._queue.extend(heartbeats)
        self.flush()

    def flush(self) -> bool:
        with self._lock:
            if not self._queue:
                return True
            batch = self._queue[:self.MAX_BATCH]
            self._queue = self._queue[self.MAX_BATCH:]
        return self._send(batch)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _send(self, heartbeats: list[dict]) -> bool:
        url = self.base_url + self.HEARTBEAT_ENDPOINT
        try:
            resp = self._session.post(url, json=heartbeats, timeout=10)
            if resp.status_code in (200, 201, 202):
                print(f"[Hackatime] ✓ {len(heartbeats)} heartbeat(s) sent")
                return True
            else:
                print(f"[Hackatime] ✗ HTTP {resp.status_code}: {resp.text[:300]}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"[Hackatime] ✗ Network error: {e}")
            return False

    def _start_flush_timer(self, interval: int) -> None:
        def _loop():
            while True:
                time.sleep(interval)
                self.flush()
        threading.Thread(target=_loop, daemon=True).start()


# ---------------------------------------------------------------------------
# Load API key
# ---------------------------------------------------------------------------

def load_api_key(config_path: Optional[str] = None) -> str:
    key = os.environ.get("HACKATIME_API_KEY") or os.environ.get("WAKATIME_API_KEY")
    if key:
        return key
    cfg = Path(config_path or Path.home() / ".wakatime.cfg")
    if cfg.exists():
        for line in cfg.read_text().splitlines():
            if line.strip().startswith("api_key"):
                _, _, value = line.partition("=")
                return value.strip()
    return ""


# ---------------------------------------------------------------------------
# Quick test — prints the exact payload being sent so you can verify
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    api_key = load_api_key()
    if not api_key:
        api_key = input("Enter your Hackatime API key: ").strip()

    client = HackatimeClient(api_key=api_key)

    # Build a test beat and show it before sending
    test_beat = {
        "entity":           "/home/rupnil/Desktop/important-improved/source_code.py",
        "type":             "file",
        "time":             time.time(),
        "is_write":         True,
        "category":         "coding",
        "language":         "Python",
        "user_agent":       client.user_agent,
        "machine":          client.machine,
        "operating_system": client.operating_system,
        "project":          "important-improved",
        "branch":           "main",
        "lineno":           42,
        "lines":            100,
        "cursorpos":        10,
    }

    print("=== Payload being sent ===")
    print(json.dumps(test_beat, indent=2))
    print(f"\n=== HTTP User-Agent header ===")
    print(client.user_agent)
    print("\nSending...")

    client._send([test_beat])
    print("\nDone! Check https://hackatime.hackclub.com — the new heartbeat")
    print("should show editor, OS, and machine correctly.")
