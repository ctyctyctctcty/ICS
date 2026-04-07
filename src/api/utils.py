import base64
import ipaddress
import json
import logging
import os
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests
import urllib3
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

USER_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
HOSTNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,253}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
POLICY_VALUE_RE = re.compile(r'^[A-Za-z0-9._:/() -]{1,255}$')


class ConfigurationError(Exception):
    pass


class ValidationError(Exception):
    pass


def load_settings() -> Dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    settings_path = root / 'config' / 'settings.json'
    env_path = root / 'config' / '.env'
    if not settings_path.exists():
        raise ConfigurationError(f'settings.json not found: {settings_path}')
    load_dotenv(env_path)
    with settings_path.open('r', encoding='utf-8') as fp:
        settings = json.load(fp)
    return settings


def setup_logger(settings: Dict[str, Any]) -> logging.Logger:
    logger = logging.getLogger('vpn_automation')
    if logger.handlers:
        return logger

    level_name = settings.get('logging', {}).get('level', 'INFO').upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)

    log_dir = Path(settings['logging']['dir'])
    if not log_dir.is_absolute():
        root = Path(__file__).resolve().parents[2]
        log_dir = root / 'data' / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime('%Y%m%d-%H%M')
    log_path = log_dir / f'run_{ts}.log'

    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')

    fh = logging.FileHandler(log_path, encoding='utf-8')
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setFormatter(formatter)
    logger.addHandler(sh)

    logger.info('Log file: %s', log_path)
    return logger


def build_basic_auth(username: str, password: str = '') -> str:
    raw = f'{username}:{password}'.encode('utf-8')
    return 'Basic ' + base64.b64encode(raw).decode('ascii')


def ensure_env() -> Dict[str, str]:
    username = os.getenv('ICS_ADMIN_USERNAME', '').strip()
    password = os.getenv('ICS_ADMIN_PASSWORD', '').strip()
    if not username or not password:
        raise ConfigurationError('ICS_ADMIN_USERNAME / ICS_ADMIN_PASSWORD must be set in config/.env')
    return {'username': username, 'password': password}


def validate_user_id(value: str) -> str:
    if value is None:
        raise ValidationError('userID is required')
    value = str(value).strip()
    if not USER_ID_RE.fullmatch(value):
        raise ValidationError(f'Invalid userID: {value}')
    return value


def validate_hostname(value: Any) -> str:
    value = '' if value is None else str(value).strip()
    if value == '' or value.lower() == 'nan':
        return ''
    if len(value) > 253 or not HOSTNAME_RE.fullmatch(value):
        raise ValidationError(f'Invalid hostname: {value}')
    return value


def validate_email(value: Any) -> str:
    value = '' if value is None else str(value).strip()
    if value == '' or value.lower() == 'nan':
        return ''
    if not EMAIL_RE.fullmatch(value):
        raise ValidationError(f'Invalid email: {value}')
    return value


def validate_ip_or_policy_value(value: Any) -> Dict[str, Any]:
    raw = '' if value is None else str(value).strip()
    if raw == '' or raw.lower() == 'nan':
        return {'kind': 'invalid', 'value': '', 'reason': 'empty'}
    if raw == 'Internet Access':
        return {'kind': 'internet_access', 'value': raw}
    if not POLICY_VALUE_RE.fullmatch(raw):
        return {'kind': 'invalid', 'value': raw, 'reason': 'contains forbidden characters'}
    try:
        ipaddress.ip_network(raw, strict=False)
        return {'kind': 'ip', 'value': raw}
    except ValueError:
        return {'kind': 'invalid', 'value': raw, 'reason': 'not a valid IP/network nor Internet Access'}


def safe_str(value: Any) -> str:
    if value is None:
        return ''
    value = str(value).strip()
    return '' if value.lower() == 'nan' else value


def role_description(name: str, company: str, email: str) -> str:
    parts = [safe_str(name), safe_str(company), safe_str(email)]
    return ' / '.join(parts)


def url_quote(value: str) -> str:
    return quote(value, safe='')


def deep_get(data: Dict[str, Any], *keys: str, default=None):
    cur = data
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def ensure_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def normalize_policy_roles_container(policy: Dict[str, Any]) -> Dict[str, Any]:
    payload = deepcopy(policy)
    roles = payload.get('roles')
    if roles is None:
        payload['roles'] = {'selected-roles': [], 'selection-type': 'selected'}
        return payload
    if isinstance(roles, list):
        payload['roles'] = {'selected-roles': roles, 'selection-type': 'selected'}
        return payload
    if isinstance(roles, dict):
        roles.setdefault('selected-roles', roles.get('selected-roles', []))
        roles.setdefault('selection-type', roles.get('selection-type', 'selected'))
        return payload
    payload['roles'] = {'selected-roles': [], 'selection-type': 'selected'}
    return payload


class APIClient:
    def __init__(self, settings: Dict[str, Any], logger: logging.Logger):
        self.settings = settings
        self.logger = logger
        self.base_url = settings['ics']['base_url'].rstrip('/')
        self.verify_ssl = settings['ics'].get('verify_ssl', False)
        self.timeout = int(settings['ics'].get('request_timeout_seconds', 30))
        creds = ensure_env()
        self.admin_username = creds['username']
        self.admin_password = creds['password']
        self.admin_realm = settings['ics']['admin_realm']
        self.api_key: Optional[str] = None
        self.session = requests.Session()
        self.session.verify = self.verify_ssl
        self.session.headers.update({'Content-Type': 'application/json'})
        self.authenticate()

    def _full_url(self, path: str) -> str:
        return f'{self.base_url}{path}'

    def _set_api_key_auth(self):
        if not self.api_key:
            raise ConfigurationError('API key is missing. Authentication failed.')
        self.session.headers['Authorization'] = build_basic_auth(self.api_key, '')

    def authenticate(self):
        endpoint = self.settings['ics']['auth_endpoint']
        url = self._full_url(endpoint)
        headers = {
            'Content-Type': 'application/json',
            'Authorization': build_basic_auth(self.admin_username, self.admin_password),
        }
        payload = {'realm': self.admin_realm}
        self.logger.info('Authenticating to ICS realm %s', self.admin_realm)
        res = requests.post(url, headers=headers, json=payload, verify=self.verify_ssl, timeout=self.timeout)
        res.raise_for_status()
        data = res.json()
        api_key = data.get('api_key')
        if not api_key:
            raise ConfigurationError(f'api_key not found in auth response: {data}')
        self.api_key = api_key
        self._set_api_key_auth()
        self.logger.info('Authentication succeeded; api_key acquired')

    def request(self, method: str, path: str, *, retry: bool = True, **kwargs) -> requests.Response:
        url = self._full_url(path)
        self.logger.debug('%s %s', method.upper(), url)

        response = self.session.request(method, url, timeout=self.timeout, **kwargs)

        if response.status_code in (401, 403) and retry:
            self.logger.warning(
                'Received %s for %s %s; refreshing authentication',
                response.status_code,
                method.upper(),
                path,
            )
            self.authenticate()
            return self.request(method, path, retry=False, **kwargs)

        if response.status_code >= 400:
            self.logger.error(
                'HTTP error %s for %s %s response=%s',
                response.status_code,
                method.upper(),
                path,
                response.text,
            )
            response.raise_for_status()

        return response

    def get_json(self, path: str) -> Dict[str, Any]:
        response = self.request('GET', path)
        if not response.text.strip():
            return {}
        return response.json()

    def post_json(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = self.request('POST', path, json=payload)
        return response.json() if response.text.strip() else {}

    def put_json(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = self.request('PUT', path, json=payload)
        return response.json() if response.text.strip() else {}
