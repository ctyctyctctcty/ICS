from typing import Any, Dict, List, Optional

from .utils import url_quote


def _collection_path(settings: Dict[str, Any]) -> str:
    return settings['ics']['endpoints']['network_connect_acl_collection']


def _create_path(settings: Dict[str, Any]) -> str:
    return _collection_path(settings).rstrip('/') + '/network-connect-acl'


def _item_path(settings: Dict[str, Any], acl_name: str) -> str:
    return settings['ics']['endpoints']['network_connect_acl_item'].format(name=url_quote(acl_name))


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


def get_all_acls(client, settings: Dict[str, Any]) -> List[Dict[str, Any]]:
    data = client.get_json(_collection_path(settings))
    return _normalize_acl_list(data)


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


def _acl_name_for_ip(ip_value: str, hostname: str) -> str:
    return f'{ip_value}({hostname})' if hostname else ip_value


def _resource_for_ip(ip_value: str) -> str:
    return f'{ip_value}:*'


def _resource_for_internet_access() -> str:
    return '*:*'


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


def _find_acl_by_ip(acls: List[Dict[str, Any]], ip_value: str) -> Optional[Dict[str, Any]]:
    for acl in acls:
        for resource_entry in _extract_resources(acl):
            if _resource_matches_ip(resource_entry, ip_value):
                return acl
    return None


def _build_acl_payload(acl_name: str, description: str, resources: List[str], roles: Optional[List[str]] = None, apply: Optional[str] = None) -> Dict[str, Any]:
    cleaned_roles = [r for r in (roles or []) if r]
    if apply is None:
        apply = 'selected' if cleaned_roles else 'all'
    return {
        'action': 'allow',
        'apply': apply,
        'description': description,
        'name': acl_name,
        'resource': resources,
        'resources-fqdn': None,
        'resources-v6': None,
        'roles': cleaned_roles if cleaned_roles else None,
        'rules': {'rule': []},
    }


def _create_acl(client, settings: Dict[str, Any], acl_payload: Dict[str, Any]) -> None:
    client.post_json(_create_path(settings), acl_payload)


def _update_acl(client, settings: Dict[str, Any], acl_payload: Dict[str, Any]) -> None:
    client.put_json(_item_path(settings, acl_payload['name']), acl_payload)


def _upsert_role_in_acl(client, settings: Dict[str, Any], logger, acl: Dict[str, Any], role_name: str, desired_resources: Optional[List[str]] = None) -> str:
    acl_name = acl.get('name', '<unknown>')
    apply_mode = str(acl.get('apply', '')).strip().lower()
    roles = _extract_roles(acl)
    current_resources = _extract_resources(acl)
    desired_resources = desired_resources or current_resources

    role_missing = role_name not in roles
    resource_changed = current_resources != desired_resources
    needs_selected = not (apply_mode == 'selected' or (apply_mode == 'all' and not roles))

    if apply_mode == 'all' and not roles and not resource_changed:
        logger.info('ACL %s already applies to all roles. skip for role %s', acl_name, role_name)
        return 'skip'

    if not role_missing and not resource_changed and not needs_selected:
        logger.info('ACL %s already contains role %s and desired resources. skip', acl_name, role_name)
        return 'skip'

    if role_missing:
        roles.append(role_name)

    payload = _build_acl_payload(
        acl_name=acl.get('name', acl_name),
        description=acl.get('description', ''),
        resources=desired_resources,
        roles=roles,
        apply='selected',
    )
    _update_acl(client, settings, payload)
    logger.info('Updated ACL %s (role added=%s, resources changed=%s)', acl_name, role_missing, resource_changed)
    return 'updated'


def handle_ip_policy(client, settings: Dict[str, Any], logger, user_id: str, hostname: str, ip_value: str) -> str:
    desired_resources = [_resource_for_ip(ip_value)]
    acls = get_all_acls(client, settings)

    existing_by_ip = _find_acl_by_ip(acls, ip_value)
    if existing_by_ip is not None:
        return _upsert_role_in_acl(client, settings, logger, existing_by_ip, user_id, desired_resources)

    acl_name = _acl_name_for_ip(ip_value, hostname)
    existing_by_name = get_acl(client, settings, acl_name)
    if existing_by_name is not None:
        return _upsert_role_in_acl(client, settings, logger, existing_by_name, user_id, desired_resources)

    payload = _build_acl_payload(
        acl_name=acl_name,
        description=f'Auto-created by vpn-automation for {ip_value}',
        resources=desired_resources,
        roles=[user_id],
        apply='selected',
    )
    _create_acl(client, settings, payload)
    logger.info('Created ACL %s and added role %s', acl_name, user_id)
    return 'created'


def handle_internet_access_policy(client, settings: Dict[str, Any], logger, user_id: str) -> str:
    existing = get_acl(client, settings, 'Internet Access')
    if existing is None:
        payload = _build_acl_payload(
            acl_name='Internet Access',
            description='Auto-created by vpn-automation for Internet Access',
            resources=[_resource_for_internet_access()],
            roles=[user_id],
            apply='selected',
        )
        _create_acl(client, settings, payload)
        logger.info('Created ACL Internet Access and added role %s', user_id)
        return 'created'
    return _upsert_role_in_acl(client, settings, logger, existing, user_id)
