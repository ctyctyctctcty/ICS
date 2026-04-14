from copy import deepcopy
from typing import Any, Dict, List, Optional

from .utils import url_quote

HOSTNAMES_MARKER = ' | hostnames: '
AUTO_DESC_PREFIX = 'Auto-created by vpn-automation for '
AUTO_NAME_SUFFIX = '__auto'


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
    """PUT-safe base name. Hostname must not be included."""
    return ip_value.replace('/', '_')


def _resource_for_ip(ip_value: str) -> str:
    return f'{ip_value}:*'


def _resource_for_internet_access() -> str:
    return '*:*'


def _normalize_resource_entry(resource_entry: str) -> str:
    entry = str(resource_entry).strip()
    for prefix in ('tcp://', 'udp://'):
        if entry.startswith(prefix):
            entry = entry[len(prefix):]
            break
    return entry


def _resource_matches_exact(resource_entry: str, ip_value: str) -> bool:
    return _normalize_resource_entry(resource_entry) == _resource_for_ip(ip_value)


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


def _acl_name(acl: Dict[str, Any]) -> str:
    return str(acl.get('name', '')).strip()


def get_acl(client, settings: Dict[str, Any], acl_name: str) -> Optional[Dict[str, Any]]:
    path = _item_path(settings, acl_name)
    response = client.session.get(client._full_url(path), timeout=client.timeout)
    if response.status_code == 404:
        return None
    if response.status_code in (401, 403):
        client.authenticate()
        response = client.session.get(client._full_url(path), timeout=client.timeout)
    response.raise_for_status()
    if not response.text.strip():
        return None
    data = response.json()
    acls = _normalize_acl_list(data)
    if acls:
        return acls[0]
    if isinstance(data, dict) and data.get('name'):
        return data
    return None


def get_all_acls(client, settings: Dict[str, Any]) -> List[Dict[str, Any]]:
    data = client.get_json(_collection_expand_path(settings))
    acls = _normalize_acl_list(data)
    detailed = []
    for acl in acls:
        if _extract_resources(acl):
            detailed.append(acl)
            continue
        name = _acl_name(acl)
        if not name:
            continue
        full = get_acl(client, settings, name)
        if full is not None:
            detailed.append(full)
    return detailed


# -----------------------------
# Description helpers
# -----------------------------

def _base_description_for_ip(ip_value: str) -> str:
    return f'{AUTO_DESC_PREFIX}{ip_value}'


def _split_description_hostnames(description: str) -> (str, List[str]):
    text = (description or '').strip()
    if not text:
        return '', []
    if HOSTNAMES_MARKER not in text:
        return text, []
    base, hosts_part = text.split(HOSTNAMES_MARKER, 1)
    hostnames = [x.strip() for x in hosts_part.split(',') if x.strip()]
    return base.strip(), hostnames


def _merge_hostname_into_description(description: str, ip_value: str, hostname: str) -> str:
    base, hostnames = _split_description_hostnames(description)
    if not base:
        base = _base_description_for_ip(ip_value)
    merged: List[str] = []
    for item in hostnames:
        if item and item not in merged:
            merged.append(item)
    if hostname and hostname not in merged:
        merged.append(hostname)
    if merged:
        return f'{base}{HOSTNAMES_MARKER}{", ".join(merged)}'
    return base


# -----------------------------
# Matching policy (IMPORTANT)
# -----------------------------

def _is_single_resource_acl_for_ip(acl: Dict[str, Any], ip_value: str) -> bool:
    resources = _extract_resources(acl)
    if len(resources) != 1:
        return False
    return _resource_matches_exact(resources[0], ip_value)


def _find_reusable_acl(acls: List[Dict[str, Any]], ip_value: str) -> Optional[Dict[str, Any]]:
    """
    Reuse ONLY if the ACL is a single-resource ACL for the exact target IP/CIDR.
    Never hijack a multi-resource ACL that merely contains the same first line.
    """
    for acl in acls:
        if _is_single_resource_acl_for_ip(acl, ip_value):
            return acl
    return None


def _find_acl_by_name(acls: List[Dict[str, Any]], acl_name: str) -> Optional[Dict[str, Any]]:
    for acl in acls:
        if _acl_name(acl) == acl_name:
            return acl
    return None


def _pick_new_acl_name(acls: List[Dict[str, Any]], ip_value: str) -> str:
    """
    Policy existence must be judged by IPv4 Resource, NOT by policy name.
    However, create still needs a unique name. If the base IP-only name already exists
    for an unrelated policy, add a safe suffix.
    """
    base = _safe_acl_name(ip_value)
    if _find_acl_by_name(acls, base) is None:
        return base

    i = 1
    while True:
        candidate = f'{base}{AUTO_NAME_SUFFIX}{i}'
        if _find_acl_by_name(acls, candidate) is None:
            return candidate
        i += 1


# -----------------------------
# ACL write helpers
# -----------------------------

def _build_acl_payload(name: str, description: str, resources: List[str], roles: List[str]) -> Dict[str, Any]:
    return {
        'action': 'allow',
        'apply': 'selected',
        'description': description,
        'name': name,
        'resource': resources,
        'resources-fqdn': None,
        'resources-v6': None,
        'roles': roles,
        'rules': {'rule': []},
    }


def _build_acl_update_payload(
    existing: Dict[str, Any],
    name: str,
    description: str,
    resources: List[str],
    roles: List[str],
) -> Dict[str, Any]:
    payload = deepcopy(existing)
    payload['name'] = name
    payload['description'] = description
    if not _extract_resources(payload):
        payload['resource'] = resources
    payload['roles'] = roles
    return payload

def _create_acl(client, settings: Dict[str, Any], payload: Dict[str, Any]) -> None:
    client.post_json(_create_path(settings), payload)


def _update_acl(client, settings: Dict[str, Any], payload: Dict[str, Any]) -> None:
    client.put_json(_item_path(settings, payload['name']), payload)


def _verify_created_acl(client, settings: Dict[str, Any], acl_name: str, ip_value: str) -> bool:
    created = get_acl(client, settings, acl_name)
    if created is None:
        return False
    return _is_single_resource_acl_for_ip(created, ip_value)


# -----------------------------
# Public handlers
# -----------------------------

def handle_ip_policy(client, settings: Dict[str, Any], logger, user_id: str, hostname: str, ip_value: str) -> str:
    desired_resources = [_resource_for_ip(ip_value)]
    acls = get_all_acls(client, settings)

    # 1) Reuse ONLY exact single-resource ACLs for this IP/CIDR.
    target = _find_reusable_acl(acls, ip_value)

    if target is not None:
        roles = _extract_roles(target)
        role_added = False
        if user_id not in roles:
            roles.append(user_id)
            role_added = True

        desired_description = _merge_hostname_into_description(target.get('description', ''), ip_value, hostname)
        description_changed = target.get('description', '') != desired_description

        if not role_added and not description_changed:
            logger.info('ACL %s already contains role %s and desired resources. skip', _acl_name(target), user_id)
            return 'skip'

        payload = _build_acl_update_payload(
            existing=target,
            name=_acl_name(target),  # keep existing canonical name
            description=desired_description,
            resources=desired_resources,
            roles=roles,
        )
        _update_acl(client, settings, payload)
        logger.info('Updated ACL %s (role added=%s, description changed=%s)', _acl_name(target), role_added, description_changed)
        return 'updated'

    # 2) No exact single-resource ACL exists.
    #    Create a NEW policy. Name collision with an unrelated policy must not block creation.
    create_name = _pick_new_acl_name(acls, ip_value)
    payload = _build_acl_payload(
        name=create_name,
        description=_merge_hostname_into_description('', ip_value, hostname),
        resources=desired_resources,
        roles=[user_id],
    )
    _create_acl(client, settings, payload)

    # Verify the created policy by IPv4 Resource, not just by name.
    if _verify_created_acl(client, settings, create_name, ip_value):
        logger.info('Created ACL %s and added role %s', create_name, user_id)
        return 'created'

    # If verification fails, surface it clearly instead of claiming success.
    raise RuntimeError(
        f'ACL create verification failed for ip={ip_value}, name={create_name}. '
        'Policy name may already exist for a different IPv4 Resource or the gateway stored unexpected resources.'
    )


def handle_internet_access_policy(client, settings: Dict[str, Any], logger, user_id: str) -> str:
    existing = get_acl(client, settings, 'Internet Access')
    if existing is None:
        payload = _build_acl_payload(
            name='Internet Access',
            description='Auto-created by vpn-automation for Internet Access',
            resources=[_resource_for_internet_access()],
            roles=[user_id],
        )
        _create_acl(client, settings, payload)
        logger.info('Created ACL Internet Access and added role %s', user_id)
        return 'created'

    roles = _extract_roles(existing)
    if user_id in roles:
        logger.info('ACL Internet Access already contains role %s and desired resources. skip', user_id)
        return 'skip'

    roles.append(user_id)
    payload = _build_acl_update_payload(
        existing=existing,
        name='Internet Access',
        description=existing.get('description', ''),
        resources=[_resource_for_internet_access()],
        roles=roles,
    )
    _update_acl(client, settings, payload)
    logger.info('Updated ACL Internet Access (role added=True, description changed=False)')
    return 'updated'
