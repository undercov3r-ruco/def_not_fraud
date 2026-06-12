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

BASE_DIR     = "/home/ruco/Desktop/waka_waka"
PROJECT_NAME = "waka_waka"
GITHUB_REPO  = "https://github.com/undercov3r-ruco/waka_waka"

# ---------------------------------------------------------------------------
# File pools
# ---------------------------------------------------------------------------
SEED_FILES = [
    "source_code.py", "main.py", "core.py", "utils.py", "models.py",
    "handlers.py", "pipeline.py", "config.py", "constants.py",
    "tests/test_core.py", "tests/test_models.py", "tests/test_pipeline.py",
    "tests/conftest.py", "scripts/setup.py", "scripts/run.py",
    "README.md", "requirements.txt", "requirements-dev.txt",
    ".gitignore", "pyproject.toml", "docs/overview.md", "docs/usage.md",
]

NEW_FILE_POOL = [
    "validators.py", "serializers.py", "exceptions.py", "middleware.py",
    "cache.py", "scheduler.py", "db.py", "auth.py", "tests/test_validators.py",
    "tests/test_auth.py", "tests/test_cache.py", "scripts/migrate.py",
    "scripts/seed.py", "utils/helpers.py", "utils/decorators.py",
    "Makefile", "docker/Dockerfile", "docker/docker-compose.yml",
    ".github/workflows/ci.yml", ".github/workflows/release.yml",
    "docs/api.md", "docs/contributing.md", "CHANGELOG.md",
]

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

def pick_pause(simulated_elapsed_seconds: float) -> tuple[str, float]:
    """Dynamically calculates pause profile weights based on ongoing cooldown targets."""
    global ultra_break_cooldown_until, ultra_pro_break_cooldown_until
    
    weights = []
    for profile in PAUSE_PROFILES:
        weight = profile["base_weight"]
        label = profile["label"]
        
        # Rule 1: If ultra break cooldown active, zero out ultra_break and ultra_pro_break
        if label in ("ultra_break", "ultra_pro_break") and simulated_elapsed_seconds < ultra_break_cooldown_until:
            weight = 0
            
        # Rule 2: If ultra pro break cooldown active, zero out ONLY ultra_pro_break
        if label == "ultra_pro_break" and simulated_elapsed_seconds < ultra_pro_break_cooldown_until:
            weight = 0
            
        weights.append(weight)

    # Pick a profile based on modified dynamic weights
    chosen_profile = random.choices(PAUSE_PROFILES, weights=weights, k=1)[0]
    label = chosen_profile["label"]
    pause_secs = random.uniform(chosen_profile["min_s"], chosen_profile["max_s"])
    
    # Calculate target time when break finishes to set cooldown start line
    break_end_sim_time = simulated_elapsed_seconds + pause_secs

    # Trigger cooldowns if a long break was rolled
    if label == "ultra_break":
        cooldown_duration = random.uniform(1 * 3600, 2 * 3600)  # 1-2 hours
        ultra_break_cooldown_until = break_end_sim_time + cooldown_duration
        logger.debug(f" [Cooldown] Ultra Break triggered. Locking Ultra/Ultra-Pro for next {cooldown_duration/3600:.2f} sim-hours.")
        
    elif label == "ultra_pro_break":
        cooldown_duration = random.uniform(2 * 3600, 6 * 3600)  # 2-6 hours
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
        if self._steps_in_direction > random.randint(3, 15):
            self._direction *= -1
            self._steps_in_direction = 0

        delta = random.randint(0, 10) * self._direction
        roll = random.random()
        
        if roll < 0.06:
            self.line = random.randint(1, max(1, self.total_lines))
            self._direction = random.choice([-1, 1])
        elif roll < 0.12:
            delta = -random.randint(1, 8)
        elif roll < 0.18:
            delta = -random.randint(10, 40)
        elif roll < 0.22:
            delta = random.randint(15, 50)

        self.line = max(1, self.line + delta)
        self.col  = random.randint(1, 120)

        if random.random() < 0.25:
            self.total_lines += random.randint(0, 4)

        if self.line > self.total_lines:
            self.total_lines = self.line + random.randint(3, 15)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
class SessionState:
    def __init__(self):
        self.active_files: list[str]  = list(SEED_FILES)
        self.new_file_pool: list[str] = list(NEW_FILE_POOL)
        self.deleted: set[str]        = set()
        self.cursor: CursorState      = CursorState(random.choice(self.active_files))
        self.heartbeats_sent          = 0
        self.simulated_elapsed        = 0.0  # Tracked accumulated simulation runtime

    def current_file(self) -> str:
        return self.cursor.filepath

    def switch_file(self):
        choices = [f for f in self.active_files if f not in self.deleted and f != self.cursor.filepath]
        if choices:
            new_file = random.choice(choices)
            self.cursor = CursorState(new_file)
            logger.info(f" ↳ switched to  {new_file}")

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
            state.cursor.move()
            file_rel = state.current_file()
            file_abs = full_path(file_rel)

            roll = random.random()
            is_write     = False
            action_label = "type"

            if roll < 0.008:
                created = state.create_file()
                if created:
                    file_rel = created
                    file_abs = full_path(created)
                    is_write = True
                    action_label = "new-file"
            elif roll < 0.015:
                state.delete_file()
                action_label = "post-delete"
            elif roll < 0.07:
                state.switch_file()
                file_rel = state.current_file()
                file_abs = full_path(file_rel)
                action_label = "switch"
            elif roll < 0.22:
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

            # Pass simulated elapsed tracker into pick_pause
            pause_label, pause_secs = pick_pause(state.simulated_elapsed)
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

    speed = float(sys.argv[1]) if len(sys.argv) > 1 else 0.05
    run(api_key, speed_factor=speed)
