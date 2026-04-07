import json
from copy import deepcopy
from typing import Any, Dict, List

from .utils import url_quote

USERNAME_DOMAIN = '@example.invalid'
BOTTOM_GROUP_TEXT = 'VPN Internet Access Only'


def realm_endpoint(settings: Dict[str, Any], realm_name: str) -> str:
    return settings['ics']['endpoints']['realm_item'].format(name=url_quote(realm_name))


def get_realm(client, settings: Dict[str, Any], realm_name: str):
    response = client.request('GET', realm_endpoint(settings, realm_name))
    return response.json() if response.text.strip() else {}


def _rules(realm: Dict[str, Any]) -> List[Dict[str, Any]]:
    return realm.setdefault('role-mapping-rules', {}).setdefault('rule', [])


def _full_username(user_id: str) -> str:
    return user_id if '@' in user_id else f'{user_id}{USERNAME_DOMAIN}'


def _is_same_user_rule(rule: Dict[str, Any], username: str, role_name: str) -> bool:
    names = rule.get('user-name', {}).get('user-names', [])
    roles = rule.get('roles', [])
    return username in names and role_name in roles


def _is_bottom_group_rule(rule: Dict[str, Any]) -> bool:
    text = json.dumps(rule, ensure_ascii=False)
    return BOTTOM_GROUP_TEXT in text


def _build_user_rule(user_id: str, role_name: str) -> Dict[str, Any]:
    username = _full_username(user_id)
    return {
        'name': role_name,
        'roles': [role_name],
        'stop-rules-processing': 'true',
        'user-name': {
            'test': 'is',
            'user-names': [username],
        },
    }


def _normalize_existing_user_rule(rule: Dict[str, Any], role_name: str) -> Dict[str, Any]:
    updated = deepcopy(rule)
    updated['name'] = role_name
    updated['roles'] = [role_name]
    updated['stop-rules-processing'] = 'true'
    return updated


def ensure_role_mapping(client, settings: Dict[str, Any], logger, realm_name: str, role_name: str) -> str:
    realm = get_realm(client, settings, realm_name)
    original_rules = _rules(realm)
    username = _full_username(role_name)

    matched_rule = None
    for rule in original_rules:
        if _is_same_user_rule(rule, username, role_name):
            matched_rule = rule
            break

    normal_rules = []
    bottom_rules = []
    changed = False

    for rule in original_rules:
        target_list = bottom_rules if _is_bottom_group_rule(rule) else normal_rules
        if matched_rule is not None and rule is matched_rule:
            normalized = _normalize_existing_user_rule(rule, role_name)
            if normalized != rule:
                changed = True
            target_list.append(normalized)
        else:
            target_list.append(deepcopy(rule))

    desired_rules = normal_rules + bottom_rules
    if desired_rules != original_rules:
        changed = True

    if matched_rule is not None:
        if changed:
            realm['role-mapping-rules']['rule'] = desired_rules
            client.put_json(realm_endpoint(settings, realm_name), realm)
            logger.info('Role mapping updated for %s in realm %s', role_name, realm_name)
            return 'updated'
        logger.info('Role mapping already exists. skip: %s', role_name)
        return 'skip'

    normal_rules.append(_build_user_rule(role_name, role_name))
    realm['role-mapping-rules']['rule'] = normal_rules + bottom_rules
    client.put_json(realm_endpoint(settings, realm_name), realm)
    insert_index = len(normal_rules) - 1
    logger.info('Role mapping inserted at index %s for %s in realm %s', insert_index, role_name, realm_name)
    return 'created'
