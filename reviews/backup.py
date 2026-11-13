import shutil
from pathlib import Path

from django.conf import settings
from django.utils import timezone


def backup_root() -> Path:
    path = Path(getattr(settings, "BACKUP_DIR", settings.BASE_DIR / "var" / "backups"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def create_backup(reason: str = "manual") -> Path:
    stamp = timezone.now().strftime("%Y%m%d-%H%M%S")
    safe_reason = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in reason)[:40]
    dest = backup_root() / f"{stamp}-{safe_reason or 'backup'}"
    dest.mkdir(parents=True, exist_ok=True)
    db_name = settings.DATABASES["default"]["NAME"]
    db_path = Path(db_name) if db_name and db_name != ":memory:" else None
    if db_path and db_path.exists():
        shutil.copy2(db_path, dest / "db.sqlite3")
    (dest / "manifest.txt").write_text(
        f"reason={reason}\ncreated={timezone.now().isoformat()}\n",
        encoding="utf-8",
    )
    prune_backups()
    return dest


def list_backups() -> list[Path]:
    if not backup_root().exists():
        return []
    return sorted(
        [path for path in backup_root().iterdir() if path.is_dir()],
        reverse=True,
    )


def latest_backup() -> Path | None:
    backups = list_backups()
    return backups[0] if backups else None


def backup_if_stale(reason: str = "auto") -> Path | None:
    latest = latest_backup()
    max_age = getattr(settings, "BACKUP_MAX_AGE_HOURS", 12)
    if latest is not None:
        created = timezone.datetime.fromtimestamp(
            latest.stat().st_mtime, tz=timezone.get_current_timezone()
        )
        age_hours = (timezone.now() - created).total_seconds() / 3600
        if age_hours < max_age:
            return None
    return create_backup(reason)


def prune_backups() -> None:
    keep = getattr(settings, "BACKUP_KEEP", 20)
    for path in list_backups()[keep:]:
        shutil.rmtree(path, ignore_errors=True)
