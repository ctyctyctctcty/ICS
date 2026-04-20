import html
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from xml.etree import ElementTree as ET

NS_MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
NS_REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
XML_NS = {'m': NS_MAIN, 'r': NS_REL}
HEADERS = ['ID', 'created_at', 'issued']
USER_ID_RE = re.compile(r'^(?:[A-Za-z]{2}(\d{4,5})|(\d{6}))$')


class CertificatePendingError(Exception):
    pass


def pending_file_path(settings: Dict[str, Any]) -> Path:
    value = settings.get('certificates', {}).get('pending_file', 'data/cert_pending/cert_pending.xlsx')
    path = Path(value)
    if path.is_absolute():
        return path
    root = Path(__file__).resolve().parents[1]
    return root / path


def certificates_enabled(settings: Dict[str, Any]) -> bool:
    return bool(settings.get('certificates', {}).get('enabled', True))


def extract_certificate_id(user_id: str) -> str:
    value = str(user_id or '').strip()
    match = USER_ID_RE.fullmatch(value)
    if not match:
        raise CertificatePendingError(
            f'Invalid userID for certificate pending list: {value}. '
            'Expected xx1234, xx12345, or 123456.'
        )
    return match.group(1) or match.group(2)


def ensure_pending_file(settings: Dict[str, Any]) -> Path:
    path = pending_file_path(settings)
    if not certificates_enabled(settings):
        return path
    if not path.exists():
        _write_rows(path, [HEADERS])
    _assert_writable(path)
    return path


def append_created_user(settings: Dict[str, Any], user_id: str) -> bool:
    if not certificates_enabled(settings):
        return False

    cert_id = extract_certificate_id(user_id)
    path = ensure_pending_file(settings)
    rows = _read_rows(path)
    if not rows:
        rows = [HEADERS]
    rows[0] = HEADERS

    existing = {row[0].strip() for row in rows[1:] if row and row[0].strip()}
    if cert_id in existing:
        return False

    rows.append([cert_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), ''])
    _write_rows(path, rows)
    return True


def _assert_writable(path: Path) -> None:
    try:
        rows = _read_rows(path)
        if not rows:
            rows = [HEADERS]
        rows[0] = HEADERS
        _write_rows(path, rows)
    except Exception as exc:
        raise CertificatePendingError(
            f'Certificate pending file is not writable: {path}. Close it in Excel and retry.'
        ) from exc


def _col_index(cell_ref: str) -> int:
    letters = ''.join(ch for ch in cell_ref if ch.isalpha()).upper()
    index = 0
    for ch in letters:
        index = index * 26 + (ord(ch) - ord('A') + 1)
    return index - 1


def _read_shared_strings(zf: zipfile.ZipFile) -> List[str]:
    if 'xl/sharedStrings.xml' not in zf.namelist():
        return []
    root = ET.fromstring(zf.read('xl/sharedStrings.xml'))
    values: List[str] = []
    for si in root.findall('m:si', XML_NS):
        values.append(''.join(t.text or '' for t in si.findall('.//m:t', XML_NS)))
    return values


def _cell_text(cell: ET.Element, shared_strings: List[str]) -> str:
    cell_type = cell.attrib.get('t')
    if cell_type == 'inlineStr':
        return ''.join(t.text or '' for t in cell.findall('.//m:t', XML_NS)).strip()
    value = cell.find('m:v', XML_NS)
    raw = value.text if value is not None and value.text is not None else ''
    if cell_type == 's':
        try:
            return shared_strings[int(raw)].strip()
        except (ValueError, IndexError):
            return ''
    return str(raw).strip()


def _read_rows(path: Path) -> List[List[str]]:
    if not path.exists():
        return []
    with zipfile.ZipFile(path) as zf:
        sheet_path = 'xl/worksheets/sheet1.xml'
        if sheet_path not in zf.namelist():
            return []
        shared_strings = _read_shared_strings(zf)
        root = ET.fromstring(zf.read(sheet_path))
        rows: List[List[str]] = []
        for row in root.findall('.//m:sheetData/m:row', XML_NS):
            values: Dict[int, str] = {}
            max_index = -1
            for cell in row.findall('m:c', XML_NS):
                idx = _col_index(cell.attrib.get('r', ''))
                values[idx] = _cell_text(cell, shared_strings)
                max_index = max(max_index, idx)
            if max_index >= 0:
                rows.append([values.get(i, '') for i in range(max_index + 1)])
    return rows


def _column_letter(index: int) -> str:
    index += 1
    letters = ''
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(ord('A') + remainder) + letters
    return letters


def _sheet_xml(rows: List[List[str]]) -> str:
    width = max(len(HEADERS), *(len(row) for row in rows)) if rows else len(HEADERS)
    height = max(1, len(rows))
    row_xml = []
    for r_idx, row in enumerate(rows, start=1):
        cells = []
        padded = row + [''] * (width - len(row))
        for c_idx, value in enumerate(padded):
            ref = f'{_column_letter(c_idx)}{r_idx}'
            safe = html.escape(str(value or ''))
            cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{safe}</t></is></c>')
        row_xml.append(f'<row r="{r_idx}">{"".join(cells)}</row>')
    dimension = f'A1:{_column_letter(width - 1)}{height}'
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="{NS_MAIN}" xmlns:r="{NS_REL}">
  <dimension ref="{dimension}"/>
  <sheetData>{''.join(row_xml)}</sheetData>
</worksheet>'''


def _write_rows(path: Path, rows: List[List[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = rows or [HEADERS]
    sheet_xml = _sheet_xml(rows)
    try:
        with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('[Content_Types].xml', '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>''')
            zf.writestr('_rels/.rels', '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>''')
            zf.writestr('xl/workbook.xml', f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="{NS_MAIN}" xmlns:r="{NS_REL}">
  <sheets><sheet name="cert_pending" sheetId="1" r:id="rId1"/></sheets>
</workbook>''')
            zf.writestr('xl/_rels/workbook.xml.rels', '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>''')
            zf.writestr('xl/worksheets/sheet1.xml', sheet_xml)
    except Exception as exc:
        raise CertificatePendingError(
            f'Certificate pending file is not writable: {path}. Close it in Excel and retry.'
        ) from exc