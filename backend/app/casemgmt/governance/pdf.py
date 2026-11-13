"""Signed PDF reports (phase CM-7): the layout, built with ReportLab (BSD) from report.report_preview's data.

Every page carries the report's ID and version, the history entry it describes and "page n of m", so a printed page can be
traced back. No fingerprints or codes are printed: the report is recorded with its ID, and anyone holding a copy can
check in Knight Hawk ("Verify a report") that it is the original.
"""

import datetime as dt
import io
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from xml.sax.saxutils import escape  # nosec B406 - only escapes text for ReportLab's markup; no XML is parsed

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# A font with wide character coverage when the system has one (the Docker image installs DejaVu); otherwise Helvetica,
# with characters it can't show replaced by "?".
FONT_CANDIDATES = [
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
]
NAVY = colors.HexColor("#0b1f3a")
LINE = colors.HexColor("#9aa7b8")
SHADE = colors.HexColor("#eef2f7")
WIDTH = A4[0] - 30 * mm


@lru_cache
def fonts() -> tuple[str, str, bool]:
    """(regular, bold, full Unicode?)"""
    for regular, bold in FONT_CANDIDATES:
        if Path(regular).exists() and Path(bold).exists():
            try:
                pdfmetrics.registerFont(TTFont("KH-Sans", regular))
                pdfmetrics.registerFont(TTFont("KH-Sans-Bold", bold))
                return "KH-Sans", "KH-Sans-Bold", True
            except Exception:  # nosec B112 - an unreadable font file: try the next one
                continue
    return "Helvetica", "Helvetica-Bold", False


def clean(value) -> str:
    """Text for a Paragraph: markup characters escaped, line breaks kept, characters the font can't show replaced."""
    text = "" if value is None else str(value)
    if not fonts()[2]:
        text = text.replace("→", "->").replace("₹", "INR ").encode("cp1252", "replace").decode("cp1252")
    return escape(text).replace("\n", "<br/>")


@dataclass
class ReportInfo:
    """What identifies this report, on every page."""

    display_id: str  # RPT-0001
    version: int
    report_type: str  # case_report / evidence_register
    title: str
    purpose: str
    generated_at: dt.datetime
    generated_by: str
    case: str  # the case number
    as_of_entry: int  # the case's history entry it describes: the case as it stood at that entry
    classification: str
    timeline: list[dict] = field(default_factory=list)
    custody: dict[str, list[dict]] = field(default_factory=dict)  # exhibit display ID -> its custody events


def _styles() -> dict[str, ParagraphStyle]:
    regular, bold, _ = fonts()
    base = ParagraphStyle("base", fontName=regular, fontSize=8.5, leading=11)
    return {
        "body": base,
        "small": ParagraphStyle("small", parent=base, fontSize=7, leading=8.6),
        "mono": ParagraphStyle("mono", parent=base, fontName="Courier", fontSize=6.0, leading=7.2),  # 32 hex digits a line
        "cell": ParagraphStyle("cell", parent=base, fontSize=7.4, leading=9),
        "head": ParagraphStyle("head", parent=base, fontName=bold, fontSize=7.4, leading=9, textColor=colors.white),
        "title": ParagraphStyle("title", parent=base, fontName=bold, fontSize=17, leading=21, textColor=NAVY),
        "subtitle": ParagraphStyle("subtitle", parent=base, fontSize=10.5, leading=13),
        "h2": ParagraphStyle("h2", parent=base, fontName=bold, fontSize=11, leading=14, textColor=NAVY, spaceBefore=10, spaceAfter=4),
        "note": ParagraphStyle("note", parent=base, fontSize=7.6, leading=9.6, textColor=colors.HexColor("#33415c")),
    }


TEAM_LABEL = {"lead": "Investigator (case lead)", "sub_investigator": "Sub Investigator", "analyst": "Analyst", "viewer": "Viewer"}


CHECK_WORDS = {"match": "Original", "mismatch": "CHANGED since it arrived", "missing": "FILE MISSING"}


def _check(last_check: dict | None) -> str:
    """The latest integrity check in plain words, with its date."""
    if not last_check:
        return "Not checked yet"
    return f"{CHECK_WORDS.get(last_check.get('result'), 'Not checked yet')}\nchecked {_when(last_check.get('checked_at'))}"


def _when(value) -> str:
    if not value:
        return "—"
    if isinstance(value, str):
        try:
            value = dt.datetime.fromisoformat(value)
        except ValueError:
            return value
    return value.astimezone(dt.UTC).strftime("%d %b %Y %H:%M UTC")


def _who(person) -> str:
    return f"{person['display_name']} (@{person['username']})" if person else "—"


def _table(header: list[str], rows: list[list], widths: list[float], st) -> Table:
    data = [[Paragraph(clean(h), st["head"]) for h in header]]
    for row in rows:
        data.append([cell if not isinstance(cell, str) else Paragraph(clean(cell), st["cell"]) for cell in row])
    table = Table(data, colWidths=[w * WIDTH for w in widths], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SHADE]),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return table


def _facts(items: list[tuple[str, object]], st) -> Table:
    rows = [[Paragraph(f"<b>{clean(k)}</b>", st["cell"]), v if not isinstance(v, str) else Paragraph(clean(v), st["cell"])]
            for k, v in items]
    table = Table(rows, colWidths=[0.24 * WIDTH, 0.76 * WIDTH])
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.3, LINE),
                               ("LEFTPADDING", (0, 0), (-1, -1), 2), ("TOPPADDING", (0, 0), (-1, -1), 2),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    return table


class _NumberedCanvas(canvas.Canvas):
    """Draws the header and footer once the number of pages is known."""

    def __init__(self, *args, info: ReportInfo, counted: dict, **kwargs):
        super().__init__(*args, **kwargs)
        self._pages: list[dict] = []
        self._info = info
        self._counted = counted

    def showPage(self):  # noqa: N802 - ReportLab's name
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._pages)
        self._counted["pages"] = total
        for state in self._pages:
            self.__dict__.update(state)
            self._decorate(total)
            super().showPage()
        super().save()

    def _decorate(self, total: int) -> None:
        regular, bold, _ = fonts()
        info, w, h = self._info, A4[0], A4[1]
        kind = "EVIDENCE REGISTER" if info.report_type == "evidence_register" else "CASE REPORT"
        self.setFillColor(NAVY)
        self.setFont(bold, 7.5)
        self.drawString(15 * mm, h - 10 * mm, f"KNIGHT HAWK · {kind}")
        self.setFont(regular, 7.5)
        self.drawRightString(w - 15 * mm, h - 10 * mm, f"Classification: {info.classification.upper()}")
        self.setStrokeColor(LINE)
        self.line(15 * mm, h - 11.5 * mm, w - 15 * mm, h - 11.5 * mm)
        self.line(15 * mm, 13 * mm, w - 15 * mm, 13 * mm)
        self.setFillColor(colors.HexColor("#33415c"))
        self.drawString(15 * mm, 9 * mm, f"{info.display_id} version {info.version} · {info.case} · as of entry {info.as_of_entry}")
        self.drawRightString(w - 15 * mm, 9 * mm, f"page {self._pageNumber} of {total}")
        self.setFont(regular, 6.5)
        self.drawString(15 * mm, 5.5 * mm, "Check a copy of this file in Knight Hawk: Verify a report. Not automatically admissible in court.")


def build(preview: dict, info: ReportInfo) -> tuple[bytes, int]:
    """The PDF's bytes and its number of pages."""
    st = _styles()
    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=16 * mm, bottomMargin=18 * mm,
                            title=f"{info.display_id} v{info.version}: {info.title}", author="Knight Hawk Case Management",
                            subject=f"{info.report_type} of {info.case} as of entry {info.as_of_entry}", creator="Knight Hawk")
    counted: dict = {}
    doc.build(_story(preview, info, st), canvasmaker=lambda *args, **kwargs: _NumberedCanvas(*args, info=info, counted=counted, **kwargs))
    return out.getvalue(), counted.get("pages", 0)


def _story(p: dict, info: ReportInfo, st) -> list:
    case = p["case"]
    register = info.report_type == "evidence_register"
    story: list = [
        Paragraph("Evidence register" if register else "Case report", st["title"]),
        Paragraph(clean(f"{case['display_id']}: {case['title']}"), st["subtitle"]),
        Spacer(1, 4 * mm),
        _facts([
            ("Report", f"{info.display_id}, version {info.version}"),
            ("Purpose", info.purpose),
            ("Generated", f"{_when(info.generated_at)} by {info.generated_by}"),
            ("Describes", f"{case['display_id']} as it stood at history entry {info.as_of_entry}"),
            ("Record integrity", f"verified: the case's history ({p['history']['entries']} entries) was re-checked just now and is unchanged"
             if p["history"]["intact"] else "NOT VERIFIED: the case's history no longer matches what was saved"),
            ("Contents", "Only what every member of the case may see. "
             + (f"{p['withheld_entries']} entr{'y is' if p['withheld_entries'] == 1 else 'ies are'} not included (sealed, or "
                "classified above the case)." if p["withheld_entries"] else "Nothing was withheld.")),
        ], st),
        Paragraph("Case identification", st["h2"]),
        _facts([
            ("Case", f"{case['display_id']}: {case['title']}"),
            ("Type and priority", f"{case['case_type'].replace('_', ' ')}, priority {case['priority']}"),
            ("Classification", case["classification"]),
            ("Status", f"workflow: {case['workflow_status'].replace('_', ' ')}; official: {case.get('official_status') or 'not recorded'}"),
            ("Jurisdiction", case.get("jurisdiction") or "not recorded"),
            ("Official references", "; ".join(case.get("references") or []) or "none recorded"),
            ("Description", case.get("description") or "—"),
        ], st),
        Paragraph("Folders", st["h2"]),
        Paragraph(clean(", ".join(p["folders"]) or "none"), st["body"]),
        Paragraph(f"Evidence ({len(p['evidence'])})", st["h2"]),
    ]
    if p["evidence"]:
        story.append(_table(
            ["Exhibit", "Collected", "Custodian", "File integrity"],
            [[f"{e['display_id']}: {e['title']}\n{e.get('folder') or ''} · {e.get('original_filename') or ''}"
              + (f"\nWithdrawn: {e.get('withdrawn_reason')}" if e.get("status") == "withdrawn" else ""),
              f"{_when(e.get('collected_at'))}\n{e.get('collected_by') or ''}\n{e.get('collection_authority') or ''}".strip(),
              ((e.get("custodian") or {}).get("name") or "—") + (" (handover pending)" if e.get("transfer_pending") else ""),
              _check(e.get("last_check"))]
             for e in p["evidence"]], [0.36, 0.26, 0.17, 0.21], st))
    else:
        story.append(Paragraph("No exhibits in the case.", st["note"]))
    if register:
        for e in p["evidence"]:
            events = info.custody.get(e["display_id"], [])
            if events:
                story.append(KeepTogether([Paragraph(clean(f"Chain of custody of {e['display_id']}"), st["h2"]), _table(
                    ["When", "Event", "From / to", "Recorded by", "Reason, method, reference"],
                    [[_when(ev["occurred_at"]), ev["label"], ev["parties"], ev["actor"], ev["details"]] for ev in events],
                    [0.17, 0.15, 0.24, 0.16, 0.28], st)]))
    else:
        story += _case_sections(p, info, st)
    i = p["integrity"]
    story += [
        Paragraph("Integrity", st["h2"]),
        Paragraph(clean(f"Latest integrity checks of the exhibits listed: {i['match']} intact, {i['mismatch']} changed, "
                        f"{i['missing']} missing, {i['never_checked']} never checked."), st["body"]),
        Spacer(1, 3 * mm),
        Paragraph("About this report", st["h2"]),
        Paragraph(clean(f"Generated by Knight Hawk from the permanent history of the case: nothing in it can be changed "
                        f"afterwards without the change being detected. This PDF file is recorded with "
                        f"{info.display_id} version {info.version}; anyone holding a copy can check in Knight Hawk "
                        f"(Verify a report) that it is the original."), st["note"]),
        Spacer(1, 2 * mm),
        Paragraph(clean(p["disclaimer"]), st["note"]),
    ]
    return story


def _case_sections(p: dict, info: ReportInfo, st) -> list:
    story: list = [Paragraph(f"Notes and analyses ({len(p['artifacts'])})", st["h2"])]
    if p["artifacts"]:
        story.append(_table(["Entry", "Kind", "Version", "Author"],
                            [[f"{a['display_id']}: {a['title']}\n{a.get('folder') or ''}"
                              + (f"\nWithdrawn: {a.get('withdrawn_reason')}" if a["status"] == "withdrawn" else ""),
                              (a.get("artifact_type") or "").replace("_", " "), f"v{a['version_number']}\n{_when(a.get('version_created_at'))}",
                              (a.get("author") or {}).get("display_name") or "—"]
                             for a in p["artifacts"]], [0.44, 0.16, 0.2, 0.2], st))
    else:
        story.append(Paragraph("None.", st["note"]))
    imports = p.get("imports") or []
    if imports:
        story += [Paragraph(f"Findings imported from other systems ({len(imports)})", st["h2"]), _table(
            ["Finding", "Source and record", "Legal authority", "Added"],
            [[f"{f['display_id']}: {f['title']}" + (" (fictional test data)" if f.get("fictional") else ""),
              f"{f.get('source') or '—'}\n{f.get('source_record_id') or ''}",
              f.get("authority_ref") or "not required by the source's policy",
              f"{(f.get('imported_by') or {}).get('display_name') or '—'}\n{_when(f.get('imported_at'))}"]
             for f in imports], [0.3, 0.25, 0.25, 0.2], st)]
    if info.timeline:
        story += [Paragraph(f"Reconstructed timeline ({len(info.timeline)} entries)", st["h2"]), _table(
            ["Date", "What", "Source"], [[t["date"], t["description"], t["source"]] for t in info.timeline], [0.13, 0.62, 0.25], st)]
    story += [Paragraph(f"Team ({len(p['team'])})", st["h2"]), _table(
        ["Person", "Part in the case", "On the case"], [[_who(m.get("user")), TEAM_LABEL.get(m.get("role"), m.get("role", "")),
                                                       f"from {_when(m.get('granted_at'))}"
                                                       + (f"\nuntil {_when(m.get('revoked_at'))}" if m.get("revoked_at") else "")]
                                                      for m in p["team"]], [0.45, 0.25, 0.3], st)]
    return story
