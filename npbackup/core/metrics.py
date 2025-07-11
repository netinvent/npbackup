#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.core.metrics"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2025 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2025061301"

import os
from typing import Optional, Tuple, List
from datetime import datetime, timezone
from logging import getLogger
from ofunctions.mailer import Mailer
from npbackup.restic_metrics import (
    create_labels_string,
    restic_str_output_to_json,
    restic_json_to_prometheus,
    upload_metrics,
    write_metrics_file,
)
from npbackup.__version__ import __intname__ as NAME, version_dict
from npbackup.__debug__ import fmt_json
from resources.customization import OEM_STRING
from npbackup.__env__ import MAX_EMAIL_DETAIL_LENGTH

logger = getLogger()


def metric_analyser(
    repo_config: dict,
    restic_result: bool,
    result_string: str,
    operation: str,
    dry_run: bool,
    append_metrics_file: bool,
    exec_time: Optional[float] = None,
    analyze_only: bool = False,
) -> Tuple[bool, bool]:
    """
    Tries to get operation success and backup to small booleans from restic output
    Returns op success, backup too small
    """
    operation_success = True
    backup_too_small = False
    timestamp = int(datetime.now(timezone.utc).timestamp())
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    metrics = []
    repo_name = repo_config.g("name")
    try:
        labels = {
            "npversion": f"{NAME}{version_dict['version']}-{version_dict['build_type']}",
            "repo_name": repo_name,
            "action": operation,
            "audience": version_dict["audience"],
            "os": version_dict["os"],
            "arch": version_dict["arch"],
        }
        if repo_config.g("global_prometheus") and repo_config.g(
            "global_prometheus.metrics"
        ):
            labels["backup_job"] = repo_config.g("prometheus.backup_job")
            labels["group"] = repo_config.g("prometheus.group")
            labels["instance"] = repo_config.g("global_prometheus.instance")
            prometheus_additional_labels = repo_config.g(
                "global_prometheus.additional_labels"
            )

            if isinstance(prometheus_additional_labels, dict):
                for k, v in prometheus_additional_labels.items():
                    labels[k] = v
            else:
                logger.error(
                    f"Bogus value in configuration for prometheus additional labels: {prometheus_additional_labels}"
                )

        # We only analyse backup output of restic
        if operation == "backup":
            minimum_backup_size_error = repo_config.g(
                "backup_opts.minimum_backup_size_error"
            )
            # If result was a str, we need to transform it into json first
            if isinstance(result_string, str):
                restic_result = restic_str_output_to_json(restic_result, result_string)

            operation_success, metrics, backup_too_small = restic_json_to_prometheus(
                restic_result=restic_result,
                restic_json=restic_result,
                labels=labels,
                minimum_backup_size_error=minimum_backup_size_error,
            )
        if not operation_success or not restic_result:
            logger.error("Backend finished with errors.")

        """
        Add a metric for informing if any warning raised while executing npbackup_tasks

        CRITICAL = 50 will be 3 in this metric, but should not really exist
        ERROR = 40 will be 2 in this metric
        WARNING = 30 will be 1 in this metric
        INFO = 20 will be 0
        """
        worst_exec_level = logger.get_worst_logger_level()
        if worst_exec_level == 50:
            exec_state = 3
        elif worst_exec_level == 40:
            exec_state = 2
        elif worst_exec_level == 30:
            exec_state = 1
        else:
            exec_state = 0

        # exec_state update according to metric_analyser
        if not operation_success or backup_too_small:
            exec_state = 2

        if not analyze_only:
            # reset worst_exec_level after getting it so we don't keep exec level between runs in the same session
            logger.set_worst_logger_level(0)

        labels_string = create_labels_string(labels)

        metrics.append(
            f'npbackup_exec_state{{{labels_string},timestamp="{timestamp}"}} {exec_state}'
        )

        # Add upgrade state if upgrades activated
        upgrade_state = os.environ.get("NPBACKUP_UPGRADE_STATE", None)
        try:
            upgrade_state = int(upgrade_state)
            labels_string = create_labels_string(labels)

            metrics.append(
                f'npbackup_exec_state{{{labels_string},timestamp="{timestamp}"}} {upgrade_state}'
            )
        except (ValueError, TypeError):
            pass
        if isinstance(exec_time, (int, float)):
            try:
                metrics.append(
                    f'npbackup_exec_time{{{labels_string},timestamp="{timestamp}"}} {exec_time}'
                )
            except (ValueError, TypeError):
                logger.warning("Cannot get exec time from environment")

        if not analyze_only:
            logger.debug("Metrics computed:\n{}".format("\n".join(metrics)))
            send_prometheus_metrics(
                repo_config,
                metrics,
                dry_run,
                append_metrics_file,
                operation,
            )
            send_metrics_mail(
                repo_config,
                operation,
                restic_result=restic_result,
                operation_success=operation_success,
                backup_too_small=backup_too_small,
                exec_state=exec_state,
                date=date,
            )
    except KeyError as exc:
        logger.info(f"Metrics error: {exc}")
        logger.debug("Trace:", exc_info=True)
    except OSError as exc:
        logger.error(f"Metrics OS error: {exc}")
        logger.debug("Trace:", exc_info=True)
    return operation_success, backup_too_small


def send_prometheus_metrics(
    repo_config: dict,
    metrics: List[str],
    dry_run: bool = False,
    append_metrics_file: bool = False,
    operation: Optional[str] = None,
) -> bool:

    try:
        no_cert_verify = repo_config.g("global_prometheus.no_cert_verify")
        if not no_cert_verify:
            no_cert_verify = False
        destination = repo_config.g("global_prometheus.destination")

        repo_name = repo_config.g("name")
        if repo_config.g("global_prometheus.metrics") is not True:
            logger.debug(
                "Metrics not enabled in configuration. Not sending metrics to Prometheus."
            )
            return False
    except KeyError as exc:
        logger.error(f"No prometheus configuration found in config file: {exc}")
        return False

    if destination and dry_run:
        logger.info("Dry run mode. Not sending metrics.")
    elif destination:
        logger.debug("Sending metrics to {}".format(destination))
        dest = destination.lower()
        if dest.startswith("http"):
            if "metrics" not in dest:
                logger.error(
                    "Destination does not contain 'metrics' keyword. Not uploading."
                )
                return False
            if "job" not in dest:
                logger.error(
                    "Destination does not contain 'job' keyword. Not uploading."
                )
                return False
            try:
                authentication = (
                    repo_config.g("global_prometheus.http_username"),
                    repo_config.g("global_prometheus.http_password"),
                )
            except KeyError:
                logger.info("No metrics authentication present.")
                authentication = None

            # Fix for #150, job name needs to be unique in order to avoid overwriting previous job in push gateway
            # destination contains the URI of the push gateway as well as the job name
            destination = f"{destination}___repo_name={repo_name}___action={operation}"
            upload_metrics(destination, authentication, no_cert_verify, metrics)
        else:
            write_metrics_file(destination, metrics, append=append_metrics_file)
        return True
    else:
        logger.debug("No metrics destination set. Not sending metrics")
    return True


def send_metrics_mail(
    repo_config: dict,
    operation: str,
    restic_result: Optional[dict] = None,
    operation_success: Optional[bool] = None,
    backup_too_small: Optional[bool] = None,
    exec_state: Optional[int] = None,
    date: Optional[int] = None,
):
    """
    Sends metrics via email.
    """

    op_success = (
        True
        if operation_success and not backup_too_small and exec_state == 0
        else False
    )

    repo_name = repo_config.g("name")
    try:
        if not repo_config.g("global_email") or not repo_config.g(
            "global_email.enable"
        ):
            logger.debug(
                "Email not enabled in configuration. Not sending notifications."
            )
            return False
        instance = repo_config.g("global_email.instance")
        smtp_server = repo_config.g("global_email.smtp_server")
        smtp_port = repo_config.g("global_email.smtp_port")
        smtp_security = repo_config.g("global_email.smtp_security")
        if not smtp_server or not smtp_port or not smtp_security:
            logger.warning(
                "SMTP server/port or security not set. Not sending notifications via email."
            )
            return False
        smtp_username = repo_config.g("global_email.smtp_username")
        smtp_password = repo_config.g("global_email.smtp_password")
        sender = repo_config.g("global_email.sender")
        recipients = repo_config.g("global_email.recipients")
        if not sender or not recipients:
            logger.warning(
                "Sender or recipients not set. Not sending metrics via email."
            )
            return False

        on_backup_success = repo_config.g("global_email.on_backup_success")
        on_backup_failure = repo_config.g("global_email.on_backup_failure")
        on_operations_success = repo_config.g("global_email.on_operations_success")
        on_operations_failure = repo_config.g("global_email.on_operations_failure")
        if operation == "backup":
            if not on_backup_success and op_success:
                logger.debug("Not sending email for backup success.")
                return True
            if not on_backup_failure and not op_success:
                logger.debug("Not sending email for backup failure.")
                return False
        elif operation != "test_email":
            if not on_operations_success and op_success:
                logger.debug("Not sending email for operation success.")
                return True
            if not on_operations_failure and not op_success:
                logger.debug("Not sending email for operation failure.")
                return False

    except KeyError as exc:
        logger.error(f"Missing email configuration: {exc}")
        return False

    logger.info(f"Sending metrics via email to {recipients}.")
    recipients = [recipient.strip() for recipient in recipients.split(",")]
    mailer = Mailer(
        smtp_server=smtp_server,
        smtp_port=smtp_port,
        security=smtp_security,
        smtp_user=smtp_username,
        smtp_password=smtp_password,
        debug=False,  # Make sure we don't send debug info so we don't get to leak passwords
    )

    subject = (
        f"{OEM_STRING} failure report for {instance} {operation} on repo {repo_name}"
    )
    body = f"Operation: {operation}\nRepo: {repo_name}"
    if op_success:
        body += "\nStatus: Success"
        subject = f"{OEM_STRING} success report for {instance} {operation} on repo {repo_name}"
    elif backup_too_small:
        body += "\nStatus: Backup too small"
    elif exec_state == 1:
        body += "\nStatus: Warning"
    elif exec_state == 2:
        body += "\nStatus: Error"
    elif exec_state == 3:
        body += "\nStatus: Critical error"

    body += f"\nDate: {date}"

    if isinstance(restic_result, dict):
        try:
            restic_result = fmt_json(restic_result)
        except TypeError:
            # TypeError may happen on ls command which contains a json of LSNodes when HAVE_MSGSPEC is True
            pass
        # Convert the dict to a string so we can analyze its length
        restic_result = str(restic_result)
        if len(restic_result) > MAX_EMAIL_DETAIL_LENGTH:
            body += f"\n\nDetail:\n{restic_result[0:MAX_EMAIL_DETAIL_LENGTH]} [... truncated]"
        else:
            body += f"\n\nDetail:\n{restic_result}"

    body += f"\n\nGenerated by {OEM_STRING} {version_dict['version']}\n"

    try:
        result = mailer.send_email(
            sender_mail=sender, recipient_mails=recipients, subject=subject, body=body
        )
        if result:
            logger.info("Metrics sent via email.")
            return True
    except Exception as exc:
        logger.error(f"Failed to send metrics via email: {exc}")
        logger.debug("Trace:", exc_info=True)
    return False
