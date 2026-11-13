import io
import re
import zipfile
from pathlib import Path

from django.core.files.base import ContentFile

from .models import Proposal, Team
from .roster import RosterError, ensure_proposal, group_sort_key
from .services import get_or_create_proposal_event


def group_id_from_name(name: str) -> str:
    text = (name or "").strip()
    number = re.search(r"(\d+)$", text)
    if number:
        return str(int(number.group(1)))
    letter = re.search(r"\b([A-Za-z])$", text)
    if letter:
        return letter.group(1).upper()
    return text


def parse_pdf_group_id(filename: str) -> str:
    stem = Path(filename).stem
    stem = re.sub(r"^(team|group)[-_\s]*", "", stem, flags=re.IGNORECASE)
    if re.fullmatch(r"\d+", stem):
        return str(int(stem))
    if re.fullmatch(r"[A-Za-z]", stem):
        return stem.upper()
    leading = re.match(r"^(\d+)", stem)
    if leading:
        return str(int(leading.group(1)))
    raise RosterError(f"Cannot read a group id from filename {filename}. Use 12.pdf or Group 12.pdf.")


def roster_group_map() -> dict[str, Team]:
    mapping = {}
    for team in Team.objects.all():
        mapping[group_id_from_name(team.name)] = team
        mapping[team.name.lower()] = team
    return mapping


def collect_pdf_uploads(files) -> list[tuple[str, bytes]]:
    collected = []
    for uploaded in files:
        name = getattr(uploaded, "name", "") or "upload.pdf"
        data = uploaded.read()
        if hasattr(uploaded, "seek"):
            uploaded.seek(0)
        if name.lower().endswith(".zip"):
            collected.extend(_pdfs_from_zip(data, name))
        elif name.lower().endswith(".pdf"):
            collected.append((name, data))
        else:
            raise RosterError(f"{name} is not a PDF or zip of PDFs.")
    if not collected:
        raise RosterError("Choose one or more PDFs, or a zip of PDFs named by group id.")
    return collected


def _pdfs_from_zip(data: bytes, zip_name: str) -> list[tuple[str, bytes]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise RosterError(f"{zip_name} is not a valid zip file.") from exc
    found = []
    for info in archive.infolist():
        if info.is_dir() or info.filename.startswith("__MACOSX/"):
            continue
        if not info.filename.lower().endswith(".pdf"):
            continue
        found.append((Path(info.filename).name, archive.read(info)))
    if not found:
        raise RosterError(f"{zip_name} has no PDF files.")
    return found


def match_pdfs_to_roster(uploads: list[tuple[str, bytes]]) -> dict:
    teams = roster_group_map()
    roster_ids = sorted(
        {group_id_from_name(team.name) for team in Team.objects.all()},
        key=lambda item: (item.isdigit(), int(item) if item.isdigit() else item),
    )
    matched = []
    extras = []
    seen = {}
    for filename, data in uploads:
        group_id = parse_pdf_group_id(filename)
        team = teams.get(group_id) or teams.get(f"group {group_id}".lower())
        if team is None:
            extras.append({"filename": filename, "group_id": group_id})
            continue
        if group_id in seen:
            raise RosterError(f"Two PDFs are named for group {group_id}: {seen[group_id]} and {filename}.")
        seen[group_id] = filename
        matched.append({"filename": filename, "group_id": group_id, "team": team, "data": data})
    missing = [
        group_id
        for group_id in roster_ids
        if group_id not in seen
    ]
    return {
        "matched": matched,
        "extras": extras,
        "missing": missing,
        "roster_ids": roster_ids,
    }


def apply_pdf_uploads(match: dict) -> int:
    event = get_or_create_proposal_event()
    updated = 0
    for item in match["matched"]:
        proposal = ensure_proposal(item["team"], event)
        proposal.title = f"{item['team'].name} proposal"
        proposal.file.save(
            proposal.download_name,
            ContentFile(item["data"]),
            save=True,
        )
        proposal.save(update_fields=["title", "file"])
        updated += 1
    return updated


def replace_group_pdf(team: Team, uploaded) -> Proposal:
    """Store one PDF on this group. A filename that names another group is rejected."""
    filename = getattr(uploaded, "name", "") or "upload.pdf"
    if not filename.lower().endswith(".pdf"):
        raise RosterError("Choose a PDF file.")
    data = uploaded.read()
    if not data:
        raise RosterError("That PDF is empty.")
    try:
        file_group = parse_pdf_group_id(filename)
    except RosterError:
        file_group = ""
    expected = group_id_from_name(team.name)
    if file_group and file_group != expected:
        raise RosterError(
            f"{filename} looks like group {file_group}, not {team.name}. "
            "Open that group's page, or rename the file."
        )
    event = get_or_create_proposal_event()
    proposal = ensure_proposal(team, event)
    proposal.title = f"{team.name} proposal"
    proposal.file.save(proposal.download_name, ContentFile(data), save=True)
    proposal.save(update_fields=["title", "file"])
    return proposal


def pdf_library_rows() -> list[dict]:
    event = get_or_create_proposal_event()
    rows = []
    for proposal in Proposal.objects.filter(event=event).select_related("team"):
        rows.append(
            {
                "team": proposal.team,
                "has_pdf": bool(proposal.file),
                "download_name": proposal.download_name,
                "stored_name": proposal.file.name if proposal.file else "",
            }
        )
    rows.sort(key=lambda row: group_sort_key(row["team"].name))
    return rows


def submission_status_by_team() -> dict[int, bool]:
    event = get_or_create_proposal_event()
    status = {}
    for proposal in Proposal.objects.filter(event=event).select_related("team"):
        status[proposal.team_id] = bool(proposal.file)
    return status
