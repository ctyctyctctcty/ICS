# VPN Automation for Ivanti Connect Secure (ICS)

## Overview
This project reads `data/input.xlsx`, authenticates to ICS using the `API Admin` realm, and performs the following for each row:

- Ensure a role named `<userID>` exists.
- Ensure the target user realm contains a role mapping rule for `<userID>@example.invalid`.
- Update or create a VPN Tunneling Access Control policy according to the Excel `IP` column.
- Write detailed logs to `data/logs/run_YYYYMMDD-HHMM.log`.

## Folder Structure

```text
vpn-automation/
│
├── config/
│   ├── settings.json
│   ├── .env
│
├── data/
│   ├── input.xlsx
│   ├── logs/
│
├── src/
│   ├── main.py
│   ├── api/
│   │   ├── auth.py
│   │   ├── roles.py
│   │   ├── role_mapping.py
│   │   ├── ip_policy.py
│   │   ├── utils.py
│   ├── excel/
│   │   ├── reader.py
│
└── README.md
```

## Prerequisites

- Python 3.10+
- Required libraries:

```bash
pip install requests python-dotenv pandas openpyxl
```

## Configuration

### 1. `config/.env`

```dotenv
ICS_ADMIN_USERNAME=apiadmin
ICS_ADMIN_PASSWORD=change-me
```

### 2. `config/settings.json`

Confirm these values for your environment:

- `base_url`
- `admin_realm` = `API Admin`
- `user_realm` = `VPN（協力会社PC）`
- `auth_endpoint` = `/api/v1/realm_auth`
- `endpoints.role_*`
- `endpoints.realm_item`
- `endpoints.vpn_policy_*`

> **Important**  
> The role and realm endpoints are aligned with Ivanti ICS REST API documentation.  
> Some firmware versions expose VPN Tunneling Access Control policy endpoints differently.  
> If your appliance uses a different resource-policy URI, update only the `vpn_policy_*` paths in `config/settings.json`.

## Excel Input Format

Create `data/input.xlsx` with the following columns:

- `userID`
- `name`
- `company`
- `email`
- `hostname`
- `IP`

### Example Values

| userID | name | company | email | hostname | IP |
|---|---|---|---|---|---|
| user001 | Test User | Example Co. | user001@example.com | pc-001 | 10.10.10.10 |
| user002 | Test User2 | Example Co. | user002@example.com | pc-002 | Internet Access |

## Execution

From the project root:

```bash
python -m src.main
```

or:

```bash
python src/main.py
```

## Behavior Details

### Authentication
- Uses `POST /api/v1/realm_auth`.
- Sends admin credentials by Basic Auth.
- Sends JSON body: `{"realm": "API Admin"}`.
- Stores returned `api_key` and uses it for subsequent Basic Auth calls.
- Automatically re-authenticates on HTTP `401` or `403`.
- SSL certificate validation is disabled by default (`verify_ssl=false`) to support self-signed certificates.

### Role Creation
- Role name = `<userID>`.
- If role already exists, it is skipped.
- Description = `name / company / email`.
- Enables:
  - Session Options
  - UI Options
  - VPN Tunneling
  - Access Features

### Role Mapping
- Target realm = `VPN（協力会社PC）`.
- Adds rule:

```text
Rule Name: <userID>
IF username is "<userID>@example.invalid"
THEN assign role "<userID>"
Stop processing = true
```

- If a rule already exists, it is skipped.
- New rules are inserted immediately above the existing bottom `Internet Access` rule when present.

### VPN Tunneling Access Control
#### Case A: IP / CIDR
- Searches existing policies that already contain the same IP/CIDR.
- If found, adds role `<userID>` idempotently.
- Otherwise creates a new policy with name:
  - `IP(hostname)` when hostname exists
  - `IP` when hostname is blank

#### Case B: `Internet Access`
- Searches for policy named `Internet Access`.
- Adds role `<userID>` idempotently.

#### Case C: Invalid value
- Logs the invalid value.
- Still executes role and role mapping.
- Skips VPN policy handling.

## Validation

The implementation enforces strict validation for:

- `userID`: `^[A-Za-z0-9._-]{1,64}$`
- `hostname`: `^[A-Za-z0-9][A-Za-z0-9.-]{0,253}$`
- `email`: basic RFC-like format check
- `IP`: valid IPv4/IPv6 host or CIDR, or exact `Internet Access`
- disallowed characters are rejected before any API call

## Notes

- The script never shells out or executes system commands.
- No SQL or command construction is used.
- All API changes are performed via `requests` JSON payloads only.
- Logging includes create/skip/error actions for traceability.
