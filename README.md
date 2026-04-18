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
ICS_ADMIN_USERNAME=your_api_account
ICS_ADMIN_PASSWORD=your_api_password
ICS_USERNAME_DOMAIN=@your.private.domain
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

## Validation

Before publishing changes to this public repo, run at least:

```powershell
python -m compileall src
```

Also scan tracked files for private values before pushing.
