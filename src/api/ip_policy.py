from typing import Any, Dict, List, Optional
from .utils import url_quote

HOSTNAMES_MARKER = ' | hostnames: '

# -----------------------------
# Path helpers
# -----------------------------

def _collection_path(settings: Dict[str, Any]) -> str:
    return settings['ics']['endpoints']['network_connect_acl_collection']


def _collection_expand_path(settings: Dict[str, Any]) -> str:
    return _collection_path(settings) + '?expand'


def _create_path(settings: Dict[str, Any]) -> str:
    return _collection_path(settings).rstrip('/') + '/network-connect-acl'


def _item_path(settings: Dict[str, Any], acl_name: str) -> str:
    return settings['ics']['endpoints']['network_connect_acl_item'].format(name=url_quote(acl_name))

# -----------------------------
# ACL name / resource helpers
# -----------------------------

def _safe_acl_name(ip_value: str) -> str:
    # PUT-safe name. Do NOT include hostname.
    return ip_value.replace('/', '_')


def _resource_for_ip(ip_value: str) -> str:
    return f'{ip_value}:*'


def _resource_for_internet_access() -> str:
    return '*:*'

# -----------------------------
# ACL fetch helpers
# -----------------------------

def _normalize_acl_list(data: Any) -> List[Dict[str, Any]]:
    if not data:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        acl_value = data.get('network-connect-acl')
        if isinstance(acl_value, list):
            return acl_value
        if isinstance(acl_value, dict):
            return [acl_value]
    return []


def _extract_resources(acl: Dict[str, Any]) -> List[str]:
    value = acl.get('resource')
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _extract_roles(acl: Dict[str, Any]) -> List[str]:
    value = acl.get('roles')
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _resource_matches_ip(resource_entry: str, ip_value: str) -> bool:
    entry = str(resource_entry).strip()
    for prefix in ('tcp://', 'udp://'):
        if entry.startswith(prefix):
            entry = entry[len(prefix):]
            break
    if ':' in entry:
        entry = entry.rsplit(':', 1)[0]
    return entry == ip_value


def get_all_acls(client, settings: Dict[str, Any]) -> List[Dict[str, Any]]:
    data = client.get_json(_collection_expand_path(settings))
    acls = _normalize_acl_list(data)
    detailed = []
    for acl in acls:
        if _extract_resources(acl):
            detailed.append(acl)
            continue
        name = acl.get('name')
        if name:
            resp = client.session.get(client._full_url(_item_path(settings, name)), timeout=client.timeout)
            if resp.status_code == 200 and resp.text.strip():
                detailed.append(resp.json())
    return detailed

# -----------------------------
# Description helpers
# -----------------------------

def _base_description_for_ip(ip_value: str) -> str:
    return f'Auto-created by vpn-automation for {ip_value}'


def _split_description_hostnames(description: str) -> (str, List[str]):
    text = (description or '').strip()
    if not text:
        return '', []
    if HOSTNAMES_MARKER not in text:
        return text, []
    base, hosts_part = text.split(HOSTNAMES_MARKER, 1)
    hosts = [x.strip() for x in hosts_part.split(',') if x.strip()]
    return base.strip(), hosts


def _merge_hostname_into_description(description: str, ip_value: str, hostname: str) -> str:
    base, hosts = _split_description_hostnames(description)
    if not base:
        base = _base_description_for_ip(ip_value)
    merged = list(dict.fromkeys(hosts + ([hostname] if hostname else [])))
    return f'{base}{HOSTNAMES_MARKER}{", ".join(merged)}' if merged else base

# -----------------------------
# ACL write helpers
# -----------------------------

def _build_acl_payload(name: str, description: str, resources: List[str], roles: List[str]) -> Dict[str, Any]:
    return {
        'action': 'allow',
        'apply': 'selected',
        'name': name,
        'description': description,
        'resource': resources,
        'roles': roles,
        'rules': {'rule': []},
    }


def _create_acl(client, settings: Dict[str, Any], payload: Dict[str, Any]):
    client.post_json(_create_path(settings), payload)


def _update_acl(client, settings: Dict[str, Any], payload: Dict[str, Any]):
    client.put_json(_item_path(settings, payload['name']), payload)

# -----------------------------
# Public handlers
# -----------------------------

def handle_ip_policy(client, settings: Dict[str, Any], logger, user_id: str, hostname: str, ip_value: str) -> str:
    desired_resource = [_resource_for_ip(ip_value)]
    safe_name = _safe_acl_name(ip_value)
    acls = get_all_acls(client, settings)

    # ✅ RESOURCE-FIRST MATCH (authoritative)
    target = None
    for acl in acls:
        for r in _extract_resources(acl):
            if _resource_matches_ip(r, ip_value):
                target = acl
                break
        if target:
            break

    description = _merge_hostname_into_description(target.get('description', '') if target else '', ip_value, hostname)

    if target:
        # ✅ NEVER create a new ACL if resource already exists
        roles = _extract_roles(target)
        if user_id not in roles:
            roles.append(user_id)
        payload = _build_acl_payload(target.get('name'), description, desired_resource, roles)
        _update_acl(client, settings, payload)
        logger.info('Updated ACL %s (resource=%s)', target.get('name'), ip_value)
        return 'updated'

    # ✅ Only here: brand-new resource
    payload = _build_acl_payload(safe_name, description, desired_resource, [user_id])
    _create_acl(client, settings, payload)
    logger.info('Created ACL %s (resource=%s)', safe_name, ip_value)
    return 'created'


def handle_internet_access_policy(client, settings: Dict[str, Any], logger, user_id: str) -> str:
    name = 'Internet Access'
    resp = client.session.get(client._full_url(_item_path(settings, name)), timeout=client.timeout)
    if resp.status_code == 200 and resp.text.strip():
        acl = resp.json()
        roles = _extract_roles(acl)
        if user_id not in roles:
            roles.append(user_id)
            payload = _build_acl_payload(name, acl.get('description', ''), [_resource_for_internet_access()], roles)
            _update_acl(client, settings, payload)
            logger.info('Updated ACL Internet Access')
            return 'updated'
        return 'skip'

    payload = _build_acl_payload(name, 'Auto-created by vpn-automation for Internet Access', [_resource_for_internet_access()], [user_id])
    _create_acl(client, settings, payload)
    logger.info('Created ACL Internet Access')
    return 'created'
