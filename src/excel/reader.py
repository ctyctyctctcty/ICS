from pathlib import Path
from typing import Dict, List

import pandas as pd

from src.api.utils import safe_str, ValidationError


def load_rows(settings: Dict) -> List[Dict]:
    excel_path = Path(settings['excel']['path'])
    if not excel_path.is_absolute():
        root = Path(__file__).resolve().parents[2]
        excel_path = root / 'data' / 'input.xlsx'

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
