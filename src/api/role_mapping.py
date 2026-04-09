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


def _is_bottom_group_rule(rule: Dict[str, Any]) -> bool:
    return BOTTOM_GROUP_TEXT in json.dumps(rule, ensure_ascii=False)


def _build_user_rule(user_id: str) -> Dict[str, Any]:
    username = _full_username(user_id)
    return {
        'name': user_id,
        'roles': [user_id],
        'stop-rules-processing': 'true',
        'user-name': {
            'test': 'is',
            'user-names': [username],
        },
    }


def ensure_role_mapping_bulk(client, settings: Dict[str, Any], logger, realm_name: str, role_names: List[str]) -> str:
    if not role_names:
        logger.info('Role mapping bulk: no targets. skip')
        return 'skip'

    realm = get_realm(client, settings, realm_name)
    rules = _rules(realm)

    # Build lookup of existing rules
    existing = set()
    for rule in rules:
        for r in rule.get('roles', []):
            for u in rule.get('user-name', {}).get('user-names', []):
                existing.add((u, r))

    # Find insert position (before Internet Access)
    insert_index = None
    for i, rule in enumerate(rules):
        if _is_bottom_group_rule(rule):
            insert_index = i
            break
    if insert_index is None:
        insert_index = len(rules)

    added = 0
    for role in role_names:
        key = (_full_username(role), role)
        if key in existing:
            continue
        rules.insert(insert_index, _build_user_rule(role))
        insert_index += 1
        added += 1

    if added == 0:
        logger.info('Role mapping bulk: nothing to add. skip')
        return 'skip'

    realm['role-mapping-rules']['rule'] = rules
    client.put_json(realm_endpoint(settings, realm_name), realm)
    logger.info('Role mapping bulk committed: %s rule(s)', added)
    return 'updated'
