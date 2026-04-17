from collections import Counter
from shutil import move

from src.api.auth import APIClient
from src.api.ip_policy import handle_internet_access_policy, handle_ip_policy
from src.api.role_mapping import ensure_role_mapping_bulk
from src.api.roles import ensure_role
from src.cert_pending import append_created_user, ensure_pending_file
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
from src.excel.reader import completed_workbook_path, ensure_excel_dirs, list_exec_workbooks, load_rows


ERROR_STATS = {'policy_invalid', 'row_validation_error', 'row_error', 'file_error', 'role_mapping_error'}


def process_workbook(client, settings, logger, workbook_path):
    logger.info('Starting workbook: %s', workbook_path)
    stats = Counter()
    role_mapping_targets = []
    rows = load_rows(settings, workbook_path)
    realm_name = settings['ics']['user_realm']
    if not rows:
        logger.error('Workbook has no data rows. file=%s', workbook_path.name)
        stats['file_error'] += 1
        return False

    for row in rows:
        row_no = row['row_number']
        raw_user_id = row['userID']
        logger.info('Processing file=%s row=%s userID=%s', workbook_path.name, row_no, raw_user_id)

        try:
            user_id = validate_user_id(raw_user_id)
            email = validate_email(row['email'])
            hostname = validate_hostname(row['hostname'])
            ip_info = validate_ip_or_policy_value(row['IP'])
            description = role_description(row['name'], row['company'], email)

            role_result = ensure_role(client, settings, logger, user_id, description)
            if role_result == 'created':
                appended = append_created_user(settings, user_id)
                logger.info('Certificate pending user %s %s', user_id, 'appended' if appended else 'already exists')
            stats[f'role_{role_result}'] += 1
            role_mapping_targets.append(user_id)

            if ip_info['kind'] == 'ip':
                policy_result = handle_ip_policy(client, settings, logger, user_id, hostname, ip_info['value'])
                stats[f'policy_{policy_result}'] += 1
            elif ip_info['kind'] == 'internet_access':
                policy_result = handle_internet_access_policy(client, settings, logger, user_id)
                stats[f'policy_{policy_result}'] += 1
            else:
                logger.error('Invalid IP value. file=%s row=%s userID=%s', workbook_path.name, row_no, user_id)
                stats['policy_invalid'] += 1

        except ValidationError as exc:
            logger.error('Validation error file=%s row=%s userID=%s: %s', workbook_path.name, row_no, raw_user_id, exc)
            stats['row_validation_error'] += 1
        except Exception as exc:
            logger.exception('Unhandled error file=%s row=%s userID=%s: %s', workbook_path.name, row_no, raw_user_id, exc)
            stats['row_error'] += 1

    try:
        mapping_result = ensure_role_mapping_bulk(client, settings, logger, realm_name, role_mapping_targets)
        stats[f'role_mapping_{mapping_result}'] += 1
    except Exception as exc:
        logger.exception('Role mapping error file=%s: %s', workbook_path.name, exc)
        stats['role_mapping_error'] += 1

    logger.info('Workbook completed: %s summary=%s', workbook_path, dict(stats))
    return not any(stats.get(key, 0) for key in ERROR_STATS)


def process():
    settings = load_settings()
    logger = setup_logger(settings)
    logger.info('Starting VPN automation')
    ensure_excel_dirs(settings)
    ensure_pending_file(settings)
    workbooks = list_exec_workbooks(settings)
    if not workbooks:
        logger.info('No Excel files found in exec folder. skip')
        return

    client = APIClient(settings, logger)
    overall_stats = Counter()

    for workbook_path in workbooks:
        try:
            succeeded = process_workbook(client, settings, logger, workbook_path)
        except Exception as exc:
            logger.exception('Workbook failed before processing completed. file=%s error=%s', workbook_path, exc)
            succeeded = False

        if succeeded:
            target_path = completed_workbook_path(settings, workbook_path)
            move(str(workbook_path), str(target_path))
            logger.info('Moved completed workbook: %s -> %s', workbook_path, target_path)
            overall_stats['workbook_completed'] += 1
        else:
            logger.warning('Workbook kept in exec folder for review: %s', workbook_path)
            overall_stats['workbook_kept_in_exec'] += 1

    logger.info('Completed. summary=%s', dict(overall_stats))


if __name__ == '__main__':
    process()
