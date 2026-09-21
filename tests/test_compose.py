"""The compose stack under the repo root: the dashboard is the only thing published, the API
stays on the internal network, cron runs the fetches, and the Claude login lives in a volume."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = yaml.safe_load((ROOT / "compose.yaml").read_text())
SERVICES = COMPOSE["services"]
VOLUMES = {"data:/var/lib/manc", "claude:/claude"}


def test_three_containers_from_two_images() -> None:
    assert set(SERVICES) == {"web", "api", "cron"}
    assert SERVICES["web"]["build"] == "site"
    assert SERVICES["api"]["build"] == SERVICES["cron"]["build"] == "."
    for service in SERVICES.values():
        assert service["restart"] == "unless-stopped"


def test_only_the_dashboard_is_published() -> None:
    assert "ports" in SERVICES["web"] and len(SERVICES["web"]["ports"]) == 1
    assert "ports" not in SERVICES["api"] and "ports" not in SERVICES["cron"]


def test_the_api_and_the_cron_share_the_database_the_login_and_the_settings() -> None:
    for name in ("api", "cron"):
        assert set(SERVICES[name]["volumes"]) == VOLUMES, name
        assert SERVICES[name]["env_file"] == ".env", name
    assert set(COMPOSE["volumes"]) == {"data", "claude"}
    assert "volumes" not in SERVICES["web"]


def test_the_api_migrates_before_serving_and_the_cron_runs_the_schedule() -> None:
    assert SERVICES["api"]["command"] == ["sh", "-c", "manc migrate && manc api"]
    assert SERVICES["cron"]["command"] == ["supercronic", "/app/crontab"]
    assert SERVICES["cron"]["depends_on"] == ["api"]  # the migration ran first
    schedule = {
        line.split(" ", 5)[5]: " ".join(line.split(" ", 5)[:5])
        for line in (ROOT / "crontab").read_text().splitlines()
        if line and not line.startswith("#")
    }
    assert schedule == {"manc fetch": "*/15 * * * *", "manc run": "0 6 * * *"}  # UTC


def test_the_image_carries_claude_with_its_login_in_the_volume() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()
    environment = dict(
        assignment.split("=", 1)
        for line in re.findall(r"^ENV (.*)$", dockerfile, re.MULTILINE)
        for assignment in line.split()
    )
    assert environment["CLAUDE_CONFIG_DIR"] == "/claude"
    assert (
        environment["DISABLE_AUTOUPDATER"] == "1"
    )  # the run never changes the claude it logged in with
    assert environment["MANC_DB_URL"] == "sqlite:////var/lib/manc/manc.db"
    assert (
        environment["MANC_API_HOST"] == "0.0.0.0"
    )  # reachable by web and cron on the internal network
    assert "claude.ai/install.sh" in dockerfile
    assert "supercronic" in dockerfile
    assert "uv sync --frozen --no-dev" in dockerfile  # the lock is what runs
    assert re.search(r"^USER manc$", dockerfile, re.MULTILINE)
    assert not re.search(r"^EXPOSE", dockerfile, re.MULTILINE)


def test_the_dashboard_image_proxies_the_api_paths_to_the_internal_service() -> None:
    dockerfile = (ROOT / "site" / "Dockerfile").read_text()
    assert "npm ci" in dockerfile and "npm run build" in dockerfile
    assert re.search(r"^FROM nginx:[\w.-]+$", dockerfile, re.MULTILINE)
    nginx = (ROOT / "site" / "nginx.conf").read_text()
    for path in ("/api/", "/health"):
        assert re.search(rf"location {re.escape(path)} \{{\s*proxy_pass http://api:8888;", nginx), (
            path
        )
    assert "try_files $uri /index.html" in nginx  # hash routing: every route is index.html


def test_the_example_env_names_every_setting() -> None:
    example = (ROOT / ".env.example").read_text()
    for name in ("MANC_PORT", "MANC_LLM_MODEL", "MISTRAL_API_KEY"):
        assert re.search(rf"^#?\s*{name}=", example, re.MULTILINE), name
    assert "MANC_DB_URL" not in example  # the image sets it; nothing to choose
