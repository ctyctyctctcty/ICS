# ICS VPN Automation

Network team tool for registering and updating ICS/VPN user roles, role mappings, and Network Connect ACL policies from Excel workbooks.

This repository is public-safe by design. Do not commit company-private configuration, real request forms, logs, generated workbooks, credentials, internal domains, internal URLs, realms, or server names.

## Repository Safety

Tracked files may contain only placeholders or sample data.

Private local files are ignored by git:

- `config/.env`
- `config/settings.json`
- `config/settings.local.json`
- `data/input.xlsx`
- `data/exec/*.xlsx`
- `data/completed/*.xlsx`
- `data/cert_pending/*.xlsx`
- `data/logs/*`

Keep `.gitkeep` files so the runtime folders exist in a fresh clone.

## First-Time Setup

Create private local config files from the public examples:

```powershell
Copy-Item config/settings.example.json config/settings.json
Copy-Item config/.env.example config/.env
```

Then fill in the private values locally. These files must not be committed.

`config/.env`:

```env
ICS_ADMIN_USERNAME=REPLACE_ME
ICS_ADMIN_PASSWORD=REPLACE_ME
ICS_USERNAME_DOMAIN=REPLACE_ME
```

`ICS_USERNAME_DOMAIN` is used when creating role mapping user-name rules. If the Excel `userID` already contains `@`, the script keeps that full username as-is.

`config/settings.json`:

- `ics.base_url`: private ICS base URL
- `ics.admin_realm`: private admin authentication realm
- `ics.user_realm`: private target user realm
- `ics.username_domain`: optional fallback if `ICS_USERNAME_DOMAIN` is not set
- `excel.exec_dir`: folder for workbooks waiting to be processed
- `excel.completed_dir`: folder for fully successful processed workbooks
- `certificates.pending_file`: local certificate pending user list

## Input Workbooks

For normal operation, put one or more `.xlsx` files into:

```text
data/exec
```

The script processes all Excel workbooks in `data/exec`.

- If a workbook finishes with no errors, it is moved to `data/completed`.
- If any row or file-level problem is detected, the workbook stays in `data/exec` for review.
- Generated certificate pending files are written under `data/cert_pending` and ignored by git.

A public sample workbook is provided as:

```text
data/input.sample.xlsx
```

Do not commit real request workbooks. `data/input.xlsx`, `data/exec/*.xlsx`, and `data/completed/*.xlsx` are ignored.

## Required Columns

Each runtime workbook must include these columns:

- `userID`
- `name`
- `company`
- `email`
- `hostname`
- `IP`

`IP` accepts either an IP/network value or `Internet Access`.

## Run

```powershell
python -m src.main
```


## Certificate Issuing Framework

Certificate issuing is separate from the ICS registration flow.

The ICS registration script writes newly created users to:

```text
data/cert_pending/cert_pending.xlsx
```

Rows whose `issued` column is blank are treated as certificate issuing targets.

The issuing framework is run separately:

```powershell
python -m src.issue_certificates
```

By default this is a dry-run. It only lists pending IDs and does not connect to the certificate server.

To actually issue certificates after filling local private settings:

```powershell
python -m src.issue_certificates --execute
```

You can limit the number of targets while testing:

```powershell
python -m src.issue_certificates --execute --limit 1
```

Private local settings are configured under `certificates.issue` in `config/settings.json`:

- `enabled`: set to `true` only when certificate issuing should be active
- `server`: certificate issuing server name
- `auth_mode`: `current_user` or `credential`
- `remote_script_path`: PowerShell script path on the certificate server
- `remote_output_dir`: folder on the certificate server where `.p12` files are generated
- `local_output_dir`: local folder where copied `.p12` files are stored
- `p12_file_pattern`: expected generated file name pattern, for example `{id}.p12`

If `auth_mode` is `credential`, set these values in local `config/.env`:

```env
CERT_SERVER_USERNAME=REPLACE_ME
CERT_SERVER_PASSWORD=REPLACE_ME
```

Generated `.p12` files under `data/certificates` are ignored by git and must not be committed.

## Validation

Before publishing changes to this public repo, run at least:

```powershell
python -m compileall src
```

Also scan tracked files for private values before pushing.
