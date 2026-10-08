"""OBS-006: obraz prod niesie SHA commita → /api/health i Sentry pokazują wdrożoną wersję
(Coolify: SOURCE_COMMIT jako build arg; bez niego zostaje „dev”)."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_dockerfile_wstrzykuje_sha():
    text = (ROOT / "Dockerfile.coolify").read_text(encoding="utf-8")
    assert "ARG SOURCE_COMMIT" in text
    assert "APP_VERSION=${SOURCE_COMMIT}" in text


def test_compose_przekazuje_source_commit():
    compose = yaml.safe_load((ROOT / "docker-compose.coolify.yml").read_text(encoding="utf-8"))
    args = compose["services"]["app"]["build"].get("args", {})
    assert "SOURCE_COMMIT" in args


def test_sentry_release_z_wersji(monkeypatch):
    from app import redaction
    monkeypatch.setattr(redaction.settings, "sentry_release", "")
    monkeypatch.setattr(redaction.settings, "app_version", "abc1234")
    assert redaction.sentry_release() == "abc1234"
    monkeypatch.setattr(redaction.settings, "app_version", "dev")
    assert redaction.sentry_release() is None
