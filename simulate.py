"""
simulate.py — Realistic IDE session simulator for Hackatime
------------------------------------------------------------
Mirrors your exact Hackatime heartbeat fingerprint:
  editor: sublime / sublime-wakatime
  OS:     linux-6.17.0-35-generic-unknown
  machine: rupnil-virtualbox
  branch: main
  dir:    /home/rupnil/Desktop/extremely-important-repo/
"""

import random
import time
import sys
import logging
from hackatime import HackatimeClient, load_api_key

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("hackatime_sim")

# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------
EDITOR_NAME      = "sublime"
EDITOR_VERSION   = "4200"
PLUGIN_NAME      = "sublime-wakatime"
PLUGIN_VERSION   = "11.1.1"
WAKATIME_VERSION = "v2.15.0"
OS_STRING        = "linux-6.17.0-35-generic-unknown"
LANGUAGE_RUNTIME = "go1.26.3"
MACHINE          = "ruco-pc"
OPERATING_SYSTEM = "linux"
BRANCH           = "main"

USER_AGENT = (
    f"wakatime/{WAKATIME_VERSION} ({OS_STRING}) {LANGUAGE_RUNTIME} "
    f"{EDITOR_NAME}/{EDITOR_VERSION} {PLUGIN_NAME}/{PLUGIN_VERSION}"
)

BASE_DIR     = "/home/ruco/Desktop/RealAI"
PROJECT_NAME = "RealAI"
GITHUB_REPO  = "https://github.com/undercov3r-ruco/RealAI"

# ---------------------------------------------------------------------------
# File pools
# ---------------------------------------------------------------------------
SEED_FILES = [
    "app.py", "realai.py", "core.py", "pipeline.py", "models.py",
    "vector_store.py", "agent.py", "config.py", "constants.py",
    "utils.py", "services/openai_service.py", "services/data_service.py",
    "tests/test_agent.py", "tests/test_pipeline.py", "tests/test_models.py",
    "tests/conftest.py", "scripts/train.py", "scripts/serve.py",
    "README.md", "requirements.txt", "pyproject.toml",
    "docs/overview.md", "docs/usage.md",
]

NEW_FILE_POOL = [
    "routes.py", "auth.py", "middleware.py", "cache.py", "scheduler.py",
    "db.py", "serializers.py", "exceptions.py", "tests/test_routes.py",
    "tests/test_auth.py", "tests/test_cache.py", "utils/helpers.py",
    "utils/decorators.py", "scripts/migrate.py", "scripts/seed.py",
    "scripts/setup.py", "services/monitoring.py", "docker/Dockerfile",
    "docker/docker-compose.yml", ".github/workflows/ci.yml",
    "docs/api.md", "docs/contributing.md", "CHANGELOG.md",
]

FILE_WEIGHTS = {
    "app.py": 10,
    "realai.py": 9,
    "core.py": 7,
    "pipeline.py": 6,
    "models.py": 6,
    "vector_store.py": 5,
    "agent.py": 5,
    "utils.py": 4,
    "config.py": 3,
    "constants.py": 2,
    "services/openai_service.py": 4,
    "services/data_service.py": 3,
    "tests/test_agent.py": 3,
    "tests/test_pipeline.py": 3,
    "tests/test_models.py": 2,
    "tests/conftest.py": 1,
    "scripts/train.py": 2,
    "scripts/serve.py": 2,
    "README.md": 1,
    "requirements.txt": 1,
    "pyproject.toml": 1,
    "docs/overview.md": 1,
    "docs/usage.md": 1,
}
SIM_START_HOUR = 9

def full_path(relative: str) -> str:
    return f"{BASE_DIR}/{relative}"

# ---------------------------------------------------------------------------
# Pause profiles & Cooldown Logic
# ---------------------------------------------------------------------------
PAUSE_PROFILES = [
    {"label": "typing",           "min_s": 2,    "max_s": 8,     "base_weight": 900},
    {"label": "think_short",      "min_s": 10,   "max_s": 25,    "base_weight": 74},
    {"label": "think_medium",     "min_s": 45,   "max_s": 120,   "base_weight": 20},
    {"label": "long_break",       "min_s": 180,  "max_s": 600,   "base_weight": 4},
    {"label": "ultra_break",      "min_s": 600,  "max_s": 1800,  "base_weight": 1},
    {"label": "ultra_pro_break",  "min_s": 1800, "max_s": 14400, "base_weight": 1},
]

# State tracking for cooldowns (in simulated seconds)
ultra_break_cooldown_until = 0.0
ultra_pro_break_cooldown_until = 0.0

def get_sim_daytime(simulated_elapsed_seconds: float) -> tuple[float, bool, bool]:
    sim_hours = simulated_elapsed_seconds / 3600.0
    hour = (SIM_START_HOUR + sim_hours) % 24
    is_night = hour >= 22 or hour < 6
    is_day = 8 <= hour < 18
    return hour, is_day, is_night


def pick_pause(state: "SessionState") -> tuple[str, float]:
    """Dynamically calculates pause profile weights based on session momentum and time of day."""
    global ultra_break_cooldown_until, ultra_pro_break_cooldown_until

    simulated_elapsed_seconds = state.simulated_elapsed
    _, is_day, is_night = get_sim_daytime(simulated_elapsed_seconds)
    session_hours = simulated_elapsed_seconds / 3600.0
    recent_breaks = state.recent_pause_labels[-8:]

    long_session_factor = 1.0 + min(1.4, max(0.0, session_hours - 3.0) * 0.18)
    focus_boost = 1.0
    if sum(1 for lbl in recent_breaks if lbl in ("think_short", "think_medium")) >= 3:
        focus_boost += 0.25
    if sum(1 for lbl in recent_breaks if lbl in ("long_break", "ultra_break", "ultra_pro_break")) >= 2:
        focus_boost += 0.35

    weights = []
    for profile in PAUSE_PROFILES:
        weight = profile["base_weight"]
        label = profile["label"]

        if label in ("ultra_break", "ultra_pro_break") and simulated_elapsed_seconds < ultra_break_cooldown_until:
            weight = 0
        if label == "ultra_pro_break" and simulated_elapsed_seconds < ultra_pro_break_cooldown_until:
            weight = 0

        if label == "typing":
            weight *= 1.0 + focus_boost * 0.2
            if is_night:
                weight *= 0.85
            elif is_day:
                weight *= 1.25
        elif label == "think_short":
            weight *= 1.0 + focus_boost * 0.2
            if is_night:
                weight *= 0.95
        elif label == "think_medium":
            weight *= 0.95
        elif label == "long_break":
            weight *= 1.0 + long_session_factor * 0.3
            if is_night:
                weight *= 1.35
            elif is_day:
                weight *= 0.85
        elif label == "ultra_break":
            weight *= 1.0 + long_session_factor * 0.45
            if is_night:
                weight *= 1.9
            elif is_day:
                weight *= 0.5
        elif label == "ultra_pro_break":
            weight *= 1.0 + long_session_factor * 0.6
            if is_night:
                weight *= 2.1
            elif is_day:
                weight *= 0.3

        weights.append(max(weight, 0.0))

    chosen_profile = random.choices(PAUSE_PROFILES, weights=weights, k=1)[0]
    label = chosen_profile["label"]
    pause_secs = random.uniform(chosen_profile["min_s"], chosen_profile["max_s"])

    break_end_sim_time = simulated_elapsed_seconds + pause_secs
    if label == "ultra_break":
        cooldown_duration = random.uniform(1 * 3600, 2 * 3600)
        ultra_break_cooldown_until = break_end_sim_time + cooldown_duration
        logger.debug(f" [Cooldown] Ultra Break triggered. Locking Ultra/Ultra-Pro for next {cooldown_duration/3600:.2f} sim-hours.")
    elif label == "ultra_pro_break":
        cooldown_duration = random.uniform(2 * 3600, 6 * 3600)
        ultra_pro_break_cooldown_until = break_end_sim_time + cooldown_duration
        logger.debug(f" [Cooldown] Ultra Pro Break triggered. Locking Ultra-Pro for next {cooldown_duration/3600:.2f} sim-hours.")

    return label, pause_secs

# ---------------------------------------------------------------------------
# Cursor state
# ---------------------------------------------------------------------------
class CursorState:
    def __init__(self, filepath: str):
        self.filepath    = filepath
        self.line        = random.randint(1, 80)
        self.col         = random.randint(1, 80)
        self.total_lines = random.randint(self.line + 10, 350)
        self._direction  = 1
        self._steps_in_direction = 0

    def move(self):
        self._steps_in_direction += 1
        if self._steps_in_direction > random.randint(4, 18):
            self._direction *= -1
            self._steps_in_direction = 0

        roll = random.random()
        if roll < 0.04:
            delta = random.randint(-8, 8)
        elif roll < 0.18:
            delta = random.randint(-3, 6) * self._direction
        elif roll < 0.38:
            delta = random.randint(-10, 10)
        else:
            delta = random.randint(-2, 5)

        if random.random() < 0.06:
            self.line = random.randint(1, max(1, self.total_lines))
            self._direction = random.choice([-1, 1])
        else:
            self.line = max(1, min(self.total_lines, self.line + delta))

        self.col = max(1, min(120, self.col + random.randint(-3, 6)))

        if random.random() < 0.12:
            self.total_lines = max(self.total_lines, self.line + random.randint(1, 3))

        if self.line > self.total_lines:
            self.total_lines = self.line + random.randint(3, 10)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
class SessionState:
    def __init__(self):
        self.active_files: list[str]  = list(SEED_FILES)
        self.new_file_pool: list[str] = list(NEW_FILE_POOL)
        self.deleted: set[str]        = set()
        self.previous_file: str | None = None
        self.quick_return_file: str | None = None
        self.recent_pause_labels: list[str] = []
        self.cursor: CursorState = CursorState(self.weighted_choice(self.active_files))
        self.heartbeats_sent = 0
        self.simulated_elapsed = 0.0  # Tracked accumulated simulation runtime

    def weighted_choice(self, choices: list[str]) -> str:
        weights = [FILE_WEIGHTS.get(path, 1) for path in choices]
        return random.choices(choices, weights=weights, k=1)[0]

    def current_file(self) -> str:
        return self.cursor.filepath

    def switch_file(self):
        choices = [f for f in self.active_files if f not in self.deleted and f != self.cursor.filepath]
        if not choices:
            return

        self.previous_file = self.cursor.filepath
        if self.previous_file in choices and random.random() < 0.35:
            new_file = self.previous_file
        else:
            new_file = self.weighted_choice(choices)

        self.cursor = CursorState(new_file)
        logger.info(f" ↳ switched to  {new_file}")

    def minor_switch(self) -> bool:
        choices = [f for f in self.active_files if f not in self.deleted and f != self.cursor.filepath]
        if not choices:
            return False

        self.previous_file = self.cursor.filepath
        target = self.weighted_choice(choices)
        self.quick_return_file = self.previous_file
        self.cursor = CursorState(target)
        logger.info(f" ↳ quick task     {target}")
        return True

    def return_from_quick_task(self) -> bool:
        if self.quick_return_file and random.random() < 0.75:
            return_path = self.quick_return_file
            self.quick_return_file = None
            self.cursor = CursorState(return_path)
            logger.info(f" ↳ returned to   {return_path}")
            return True
        return False

    def create_file(self) -> str | None:
        available = [f for f in self.new_file_pool if f not in self.active_files]
        if not available:
            return None
        new_file = random.choice(available)
        self.active_files.append(new_file)
        self.cursor = CursorState(new_file)
        self.cursor.line = 1
        logger.info(f" ✚ created       {new_file}")
        return new_file

    def delete_file(self) -> str | None:
        candidates = [f for f in self.active_files if f != self.cursor.filepath and f not in self.deleted]
        if len(candidates) < 2:
            return None
        victim = random.choice(candidates)
        self.deleted.add(victim)
        self.active_files.remove(victim)
        logger.info(f" ✖ deleted       {victim}")
        return victim

    def record_pause(self, label: str) -> None:
        self.recent_pause_labels.append(label)
        if len(self.recent_pause_labels) > 12:
            self.recent_pause_labels.pop(0)

    def elapsed_str(self) -> str:
        s = int(self.simulated_elapsed)
        return f"{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}"

# ---------------------------------------------------------------------------
# Main simulation loop
# ---------------------------------------------------------------------------
def run(api_key: str, speed_factor: float = 1.0):
    client = HackatimeClient(
        api_key=api_key,
        editor_name=EDITOR_NAME,
        editor_version=EDITOR_VERSION,
        plugin_name=PLUGIN_NAME,
        plugin_version=PLUGIN_VERSION,
        wakatime_version=WAKATIME_VERSION,
        os_string=OS_STRING,
        operating_system=OPERATING_SYSTEM,
        language_runtime=LANGUAGE_RUNTIME,
        machine=MACHINE,
        auto_flush_interval=0,
    )

    state = SessionState()
    tick  = 0

    logger.warning("=================================================================")
    logger.warning("  Hackatime Simulator")
    logger.warning(f"  Project  : {PROJECT_NAME}")
    logger.warning(f"  Repo     : {GITHUB_REPO}")
    logger.warning(f"  Editor   : {EDITOR_NAME} {EDITOR_VERSION}")
    logger.warning(f"  Machine  : {MACHINE}  |  OS: {OPERATING_SYSTEM}")
    logger.warning(f"  Branch   : {BRANCH}")
    logger.warning(f"  UA       : {USER_AGENT}")
    logger.warning(f"  Speed    : {1/speed_factor:.0f}x real-time")
    logger.warning("=================================================================")

    try:
        while True:
            tick += 1
            returned = state.return_from_quick_task()
            state.cursor.move()
            file_rel = state.current_file()
            file_abs = full_path(file_rel)

            roll = random.random()
            is_write = False
            action_label = "type"

            if returned:
                action_label = "return"
            elif roll < 0.006:
                created = state.create_file()
                if created:
                    file_rel = created
                    file_abs = full_path(created)
                    is_write = True
                    action_label = "new-file"
            elif roll < 0.011:
                state.delete_file()
                file_rel = state.current_file()
                file_abs = full_path(file_rel)
                action_label = "post-delete"
            elif roll < 0.028:
                if state.minor_switch():
                    file_rel = state.current_file()
                    file_abs = full_path(file_rel)
                    action_label = "quick"
            elif roll < 0.050:
                state.switch_file()
                file_rel = state.current_file()
                file_abs = full_path(file_rel)
                action_label = "switch"
            elif roll < 0.18:
                is_write = True
                action_label = "save"

            client.heartbeat(
                file=file_abs,
                project=PROJECT_NAME,
                language="Python" if file_rel.endswith(".py") else None,
                branch=BRANCH,
                is_write=is_write,
                line_number=state.cursor.line,
                cursor_pos=state.cursor.col,
                lines=state.cursor.total_lines,
            )
            state.heartbeats_sent += 1

            logger.info(
                f"[{state.elapsed_str()}] tick={tick:>5}  {action_label:<12} "
                f"{file_rel:<38}  line={state.cursor.line:<5} col={state.cursor.col:<4} "
                f"{'💾' if is_write else '  '}"
            )

            if is_write or state.heartbeats_sent % 10 == 0:
                client.flush()

            # Pick a pause based on session state and time of day
            pause_label, pause_secs = pick_pause(state)
            state.record_pause(pause_label)
            scaled = pause_secs * speed_factor

            if pause_label != "typing":
                logger.warning(f" ⏸  {pause_label}  ({pause_secs:.0f}s real -> {scaled:.1f}s sleep)")

            # Advance simulated time tracker
            state.simulated_elapsed += pause_secs
            time.sleep(scaled)

    except KeyboardInterrupt:
        logger.warning(f"Stopped after {tick} ticks. Flushing...")
        client.flush()
        logger.info(f"Total heartbeats sent: {state.heartbeats_sent}")
        logger.info("Done ✓")

if __name__ == "__main__":
    api_key = load_api_key()
    if not api_key:
        api_key = input("Enter your Hackatime API key: ").strip()

    speed = float(sys.argv[1]) if len(sys.argv) > 1 else 0.2
    run(api_key, speed_factor=speed)
