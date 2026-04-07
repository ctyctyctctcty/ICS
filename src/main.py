from collections import Counter

from src.api.auth import APIClient
from src.api.ip_policy import handle_internet_access_policy, handle_ip_policy
from src.api.role_mapping import ensure_role_mapping
from src.api.roles import ensure_role
from src.api.utils import (
    ValidationError,
    load_settings,
    role_description,
    setup_logger,
    validate_email,
    validate_hostname,
    validate_ip_or_policy_value,
    validate_user_id,
)
from src.excel.reader import load_rows


def process():
    settings = load_settings()
    logger = setup_logger(settings)
    logger.info('Starting VPN automation')
    client = APIClient(settings, logger)
    rows = load_rows(settings)
    realm_name = settings['ics']['user_realm']
    stats = Counter()

    for row in rows:
        row_no = row['row_number']
        raw_user_id = row['userID']
        logger.info('Processing row=%s userID=%s', row_no, raw_user_id)

        try:
            user_id = validate_user_id(raw_user_id)
            email = validate_email(row['email'])
            hostname = validate_hostname(row['hostname'])
            ip_info = validate_ip_or_policy_value(row['IP'])
            description = role_description(row['name'], row['company'], email)

            role_result = ensure_role(client, settings, logger, user_id, description)
            stats[f'role_{role_result}'] += 1

            mapping_result = ensure_role_mapping(client, settings, logger, realm_name, user_id)
            stats[f'mapping_{mapping_result}'] += 1

            if ip_info['kind'] == 'ip':
                policy_result = handle_ip_policy(client, settings, logger, user_id, hostname, ip_info['value'])
                stats[f'policy_{policy_result}'] += 1
            elif ip_info['kind'] == 'internet_access':
                policy_result = handle_internet_access_policy(client, settings, logger, user_id)
                stats[f'policy_{policy_result}'] += 1
            else:
                logger.error('Invalid IP value. row=%s userID=%s value=%s reason=%s; role and role mapping were still processed.', row_no, user_id, ip_info.get('value'), ip_info.get('reason'))
                stats['policy_invalid'] += 1

        except ValidationError as exc:
            logger.error('Validation error row=%s userID=%s: %s', row_no, raw_user_id, exc)
            stats['row_validation_error'] += 1
        except Exception as exc:
            logger.exception('Unhandled error row=%s userID=%s: %s', row_no, raw_user_id, exc)
            stats['row_error'] += 1

    logger.info('Completed. summary=%s', dict(stats))


if __name__ == '__main__':
    process()
