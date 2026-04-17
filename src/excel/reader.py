from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from src.api.utils import safe_str, ValidationError


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_data_path(value: str, default_relative: str) -> Path:
    path = Path(value or default_relative)
    if path.is_absolute():
        return path
    return _root() / path


def exec_dir(settings: Dict) -> Path:
    return _resolve_data_path(settings['excel'].get('exec_dir', 'data/exec'), 'data/exec')


def completed_dir(settings: Dict) -> Path:
    return _resolve_data_path(settings['excel'].get('completed_dir', 'data/completed'), 'data/completed')


def ensure_excel_dirs(settings: Dict) -> None:
    exec_dir(settings).mkdir(parents=True, exist_ok=True)
    completed_dir(settings).mkdir(parents=True, exist_ok=True)


def list_exec_workbooks(settings: Dict) -> List[Path]:
    ensure_excel_dirs(settings)
    return sorted(
        path for path in exec_dir(settings).glob('*.xlsx')
        if path.is_file() and not path.name.startswith('~$')
    )


def completed_workbook_path(settings: Dict, source_path: Path) -> Path:
    target_dir = completed_dir(settings)
    target = target_dir / source_path.name
    if not target.exists():
        return target

    stem = source_path.stem
    suffix = source_path.suffix
    index = 1
    while True:
        candidate = target_dir / f'{stem}_{index}{suffix}'
        if not candidate.exists():
            return candidate
        index += 1


def load_rows(settings: Dict, excel_path: Optional[Path] = None) -> List[Dict]:
    if excel_path is None:
        legacy_path = settings['excel'].get('path', 'data/input.xlsx')
        excel_path = _resolve_data_path(legacy_path, 'data/input.xlsx')
    else:
        excel_path = Path(excel_path)

    if not excel_path.exists():
        raise FileNotFoundError(f'Excel file not found: {excel_path}')

    df = pd.read_excel(excel_path, engine='openpyxl')
    required = settings['excel']['required_columns']
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValidationError(f'Missing required columns: {missing}')

    records = []
    for idx, row in df.iterrows():
        record = {
            'row_number': idx + 2,
            'userID': safe_str(row.get('userID')),
            'name': safe_str(row.get('name')),
            'company': safe_str(row.get('company')),
            'email': safe_str(row.get('email')),
            'hostname': safe_str(row.get('hostname')),
            'IP': safe_str(row.get('IP'))
        }
        records.append(record)
    return records
