import argparse
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.api.utils import ConfigurationError, load_settings, setup_logger
from src.cert_pending import mark_certificate_issued, pending_certificate_ids


class CertificateIssueError(Exception):
    pass


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _issue_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    return settings.get('certificates', {}).get('issue', {})


def _resolve_path(value: str, default_relative: str) -> Path:
    path = Path(value or default_relative)
    if path.is_absolute():
        return path
    return _root() / path


def local_output_dir(settings: Dict[str, Any]) -> Path:
    issue = _issue_settings(settings)
    return _resolve_path(issue.get('local_output_dir', 'data/certificates'), 'data/certificates')


def _required(issue: Dict[str, Any], key: str) -> str:
    value = str(issue.get(key, '')).strip()
    if not value or value == 'REPLACE_ME':
        raise ConfigurationError(f'certificates.issue.{key} must be set in config/settings.json')
    return value


def _quote_ps(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _remote_script(cert_id: str, settings: Dict[str, Any]) -> str:
    issue = _issue_settings(settings)
    server = _required(issue, 'server')
    remote_script_path = _required(issue, 'remote_script_path')
    remote_output_dir = _required(issue, 'remote_output_dir')
    local_dir = str(local_output_dir(settings))
    p12_pattern = str(issue.get('p12_file_pattern', '{id}.p12') or '{id}.p12')
    remote_file_name = p12_pattern.format(id=cert_id)
    auth_mode = str(issue.get('auth_mode', 'current_user')).strip().lower()

    lines: List[str] = [
        '$ErrorActionPreference = "Stop"',
        f'$Server = {_quote_ps(server)}',
        f'$CertId = {_quote_ps(cert_id)}',
        f'$RemoteScriptPath = {_quote_ps(remote_script_path)}',
        f'$RemoteOutputDir = {_quote_ps(remote_output_dir)}',
        f'$RemoteFileName = {_quote_ps(remote_file_name)}',
        f'$LocalOutputDir = {_quote_ps(local_dir)}',
        'New-Item -ItemType Directory -Force -Path $LocalOutputDir | Out-Null',
    ]

    if auth_mode == 'credential':
        username_env = str(issue.get('username_env', 'CERT_SERVER_USERNAME'))
        password_env = str(issue.get('password_env', 'CERT_SERVER_PASSWORD'))
        lines.extend([
            f'$Username = [Environment]::GetEnvironmentVariable({_quote_ps(username_env)})',
            f'$PasswordText = [Environment]::GetEnvironmentVariable({_quote_ps(password_env)})',
            'if ([string]::IsNullOrWhiteSpace($Username) -or [string]::IsNullOrWhiteSpace($PasswordText)) { throw "Certificate server credential env vars are missing." }',
            '$SecurePassword = ConvertTo-SecureString $PasswordText -AsPlainText -Force',
            '$Credential = New-Object System.Management.Automation.PSCredential($Username, $SecurePassword)',
            '$Session = New-PSSession -ComputerName $Server -Credential $Credential',
        ])
    elif auth_mode == 'current_user':
        lines.append('$Session = New-PSSession -ComputerName $Server')
    else:
        raise ConfigurationError('certificates.issue.auth_mode must be current_user or credential')

    lines.extend([
        'try {',
        '  Invoke-Command -Session $Session -ScriptBlock {',
        '    param($RemoteScriptPath, $CertId, $RemoteOutputDir)',
        '    & $RemoteScriptPath -UserId $CertId -OutputDirectory $RemoteOutputDir',
        '  } -ArgumentList $RemoteScriptPath, $CertId, $RemoteOutputDir',
        '  $RemoteP12 = Join-Path $RemoteOutputDir $RemoteFileName',
        '  $LocalP12 = Join-Path $LocalOutputDir $RemoteFileName',
        '  Copy-Item -FromSession $Session -Path $RemoteP12 -Destination $LocalP12 -Force',
        '  if (-not (Test-Path $LocalP12)) { throw "P12 file was not copied back: $LocalP12" }',
        '  Write-Output $LocalP12',
        '} finally {',
        '  if ($Session) { Remove-PSSession $Session }',
        '}',
    ])
    return '\n'.join(lines)


def issue_one_certificate(cert_id: str, settings: Dict[str, Any], logger) -> Path:
    issue = _issue_settings(settings)
    powershell_exe = str(issue.get('powershell_exe', 'powershell.exe') or 'powershell.exe')
    script = _remote_script(cert_id, settings)
    logger.info('Issuing certificate for ID=%s', cert_id)
    result = subprocess.run(
        [powershell_exe, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', script],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.stdout.strip():
        logger.info('PowerShell stdout for %s: %s', cert_id, result.stdout.strip())
    if result.stderr.strip():
        logger.warning('PowerShell stderr for %s: %s', cert_id, result.stderr.strip())
    if result.returncode != 0:
        raise CertificateIssueError(f'Certificate issue failed for {cert_id}: exit={result.returncode}')

    output_lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not output_lines:
        raise CertificateIssueError(f'Certificate issue did not return a local p12 path for {cert_id}')
    local_p12 = Path(output_lines[-1])
    if not local_p12.exists():
        raise CertificateIssueError(f'Copied p12 file not found for {cert_id}: {local_p12}')
    return local_p12


def process(execute: bool = False, limit: Optional[int] = None) -> None:
    settings = load_settings()
    logger = setup_logger(settings)
    issue = _issue_settings(settings)
    if not bool(issue.get('enabled', False)):
        logger.info('Certificate issuing is disabled. Set certificates.issue.enabled=true to use this script.')
        return

    ids = pending_certificate_ids(settings)
    if limit is not None:
        ids = ids[:limit]
    if not ids:
        logger.info('No pending certificate IDs found. skip')
        return

    logger.info('Pending certificate IDs: %s', ids)
    if not execute:
        logger.info('Dry-run only. Re-run with --execute to issue certificates.')
        return

    local_output_dir(settings).mkdir(parents=True, exist_ok=True)
    for cert_id in ids:
        try:
            local_p12 = issue_one_certificate(cert_id, settings, logger)
            mark_certificate_issued(settings, cert_id)
            logger.info('Certificate issued and marked: ID=%s file=%s', cert_id, local_p12)
        except Exception as exc:
            logger.exception('Certificate issuing failed for ID=%s: %s', cert_id, exc)


def main() -> None:
    parser = argparse.ArgumentParser(description='Issue VPN certificates for rows in cert_pending.xlsx with blank issued column.')
    parser.add_argument('--execute', action='store_true', help='Actually remote to the certificate server and issue certificates. Default is dry-run.')
    parser.add_argument('--limit', type=int, default=None, help='Process at most N pending IDs.')
    args = parser.parse_args()
    process(execute=args.execute, limit=args.limit)


if __name__ == '__main__':
    main()
