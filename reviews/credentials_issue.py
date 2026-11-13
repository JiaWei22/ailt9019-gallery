import csv
import io
from pathlib import Path

from .roster import RosterError, normalize_group_name
from .services import generate_login_password, generate_reviewer_code


SOURCE_ALIASES = {
    "name": {"name", "student name", "full name", "student"},
    "uid": {
        "uid",
        "student_id",
        "student id",
        "student_number",
        "student number",
        "hku uid",
        "university id",
    },
    "email": {"email", "hku email", "mail", "e-mail"},
    "group": {
        "group",
        "team",
        "group_name",
        "group name",
        "group_id",
        "group id",
        "group_number",
        "group number",
    },
}


def parse_source_roster(uploaded) -> list[dict]:
    """Parse a raw course list. Reviewer IDs and passwords are not required."""
    name = (getattr(uploaded, "name", "") or "").lower()
    data = uploaded.read()
    if hasattr(uploaded, "seek"):
        uploaded.seek(0)
    if name.endswith(".xlsx"):
        from .roster import _parse_xlsx

        rows = _parse_xlsx(data)
    else:
        text = data.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise RosterError("The file is empty.")
    headers = [(cell or "").strip().lower() for cell in rows[0]]
    found = {}
    for index, header in enumerate(headers):
        for field, aliases in SOURCE_ALIASES.items():
            if header in aliases:
                found[field] = index
    missing = [field for field in ("name", "uid", "group") if field not in found]
    if missing:
        raise RosterError(
            "The source file needs columns: name, uid/student_number, group/group_name. Missing: "
            + ", ".join(missing)
        )
    records = []
    seen = set()
    for line_no, row in enumerate(rows[1:], start=2):
        if not any(str(cell).strip() for cell in row if cell is not None):
            continue
        record = {
            "name": _cell(row, found["name"]),
            "uid": _cell(row, found["uid"]),
            "email": _cell(row, found.get("email")).lower(),
            "group": normalize_group_name(_cell(row, found["group"])),
        }
        if not record["name"] or not record["uid"]:
            raise RosterError(f"Row {line_no} is missing name or UID.")
        if record["uid"] in seen:
            raise RosterError(f"UID {record['uid']} is repeated in the file.")
        seen.add(record["uid"])
        records.append(record)
    if not records:
        raise RosterError("The file has a header but no students.")
    return records


def _cell(row: list, index: int | None) -> str:
    if index is None or index >= len(row) or row[index] is None:
        return ""
    return str(row[index]).strip()


def issue_credentials(records: list[dict]) -> list[dict]:
    codes: set[str] = set()
    issued = []
    for record in records:
        code = generate_reviewer_code(codes)
        codes.add(code)
        group = record.get("group") or ""
        if group and not group.lower().startswith("group"):
            group = normalize_group_name(group)
        issued.append(
            {
                "name": record["name"],
                "uid": record["uid"],
                "email": record.get("email") or "",
                "group": group,
                "reviewer_id": code,
                "password": generate_login_password(),
            }
        )
    return issued


def credentials_table_bytes(rows: list[dict], *, fmt: str = "csv") -> bytes:
    headers = ["name", "uid", "email", "group", "reviewer_id", "password"]
    if fmt == "xlsx":
        from openpyxl import Workbook

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "credentials"
        sheet.append(headers)
        for row in rows:
            sheet.append([row.get(key, "") for key in headers])
        buffer = io.BytesIO()
        workbook.save(buffer)
        return buffer.getvalue()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([row.get(key, "") for key in headers])
    return buffer.getvalue().encode("utf-8")


def issue_file(source_path: Path, dest_path: Path) -> list[dict]:
    with source_path.open("rb") as handle:
        class _Upload:
            name = source_path.name

            def __init__(self, data):
                self._data = data

            def read(self):
                return self._data

            def seek(self, *_args):
                return None

        records = parse_source_roster(_Upload(handle.read()))
    rows = issue_credentials(records)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    fmt = "xlsx" if dest_path.suffix.lower() == ".xlsx" else "csv"
    dest_path.write_bytes(credentials_table_bytes(rows, fmt=fmt))
    return rows
