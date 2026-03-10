#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.core.monitoring.email"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2026 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2025112701"

from typing import Dict, Any, Optional, List
from logging import getLogger
from ofunctions.mailer import Mailer
from npbackup.core.monitoring import MonitoringBackend
from npbackup.__debug__ import fmt_json
from resources.customization import OEM_STRING
from npbackup.__env__ import MAX_EMAIL_DETAIL_LENGTH
from npbackup.__version__ import version_dict

logger = getLogger()


class EmailMonitor(MonitoringBackend):
    """
    Email monitoring backend implementation
    Sends email notifications based on backup success/failure
    """

    def __init__(self, repo_config: dict, monitoring_config: dict):
        """
        Initialize Email monitoring backend

        Args:
            repo_config: Repository configuration dictionary
        """
        super().__init__(repo_config, monitoring_config)

    def is_enabled(self) -> bool:
        return self.get_monitoring_value("global_email.enabled", False)

    def send_metrics(
        self,
        metrics: Dict[str, Any],
        labels: Dict[str, str],
        operation: str,
        dry_run: bool = False,
    ) -> bool:
        """
        Send metrics via email notification

        Args:
            metrics: Dictionary of metric names and values
            labels: Dictionary of labels/tags for the metrics
            operation: Operation name (backup, restore, etc.)
            dry_run: If True, don't actually send email

        Returns:
            True if successful, False otherwise
        """
        if not self.is_enabled():
            logger.debug(
                "Email not enabled in configuration. Not sending notifications."
            )
            return False

        labels = {**labels, **self.base_labels}

        # Determine if operation was successful
        exec_state = metrics.get("exec_state", 0)
        operation_success = metrics.get("operation_success", 1)
        backup_too_small = metrics.get("backup_too_small", 0)

        op_success = (
            operation_success == 1 and backup_too_small == 0 and exec_state == 0
        )

        # Get email configuration
        try:
            instance = self.get_monitoring_value("global_email.instance")
            smtp_server = self.get_monitoring_value("global_email.smtp_server")
            smtp_port = self.get_monitoring_value("global_email.smtp_port")
            smtp_security = self.get_monitoring_value("global_email.smtp_security")

            if not smtp_server or not smtp_port or not smtp_security:
                logger.warning(
                    "SMTP server/port or security not set. Not sending notifications via email."
                )
                return False

            smtp_username = self.get_monitoring_value("global_email.smtp_username")
            smtp_password = self.get_monitoring_value("global_email.smtp_password")
            sender = self.get_monitoring_value("global_email.sender")

            if not sender:
                logger.warning("Sender not set. Not sending metrics via email.")
                return False

            # Determine which recipients list to use based on operation and result
            recipients_to_send = []
            if operation == "backup":
                if op_success:
                    # Check for specific backup success recipients
                    for recipient in self.get_monitoring_value(
                        "global_email.recipients.on_backup_success", []
                    ):
                        if recipient not in recipients_to_send:
                            recipients_to_send.append(recipient)
                else:
                    # Check for specific backup failure recipients
                    for recipient in self.get_monitoring_value(
                        "global_email.recipients.on_backup_failure", []
                    ):
                        if recipient not in recipients_to_send:
                            recipients_to_send.append(recipient)
            else:
                if op_success:
                    for recipient in self.get_monitoring_value(
                        "global_email.recipients.on_operations_success", []
                    ):
                        if recipient not in recipients_to_send:
                            recipients_to_send.append(recipient)
                else:
                    for recipient in self.get_monitoring_value(
                        "global_email.recipients.on_operations_failure", []
                    ):
                        if recipient not in recipients_to_send:
                            recipients_to_send.append(recipient)

            if not recipients_to_send:
                logger.warning(
                    f"No recipients configured for {operation} {'success' if op_success else 'failure'}. "
                    "Not sending metrics via email."
                )
                return False

        except KeyError as exc:
            logger.error(f"Missing email configuration: {exc}")
            return False

        if dry_run:
            logger.info("Dry run mode. Not sending email.")
            return True

        # Build and send the email
        logger.debug(
            f"Sending email notification to {smtp_server}:{smtp_port} with security {smtp_security} using {'authentication' if smtp_username and smtp_password else 'no authentication'}."
        )
        for recipient in recipients_to_send:
            logger.debug(f"Adding recipient {recipient} for email notification.")
            result = self._send_email(
                smtp_server=smtp_server,
                smtp_port=smtp_port,
                smtp_security=smtp_security,
                smtp_username=smtp_username,
                smtp_password=smtp_password,
                sender=sender,
                recipients=recipients_to_send,
                instance=instance,
                operation=operation,
                metrics=metrics,
                labels=labels,
                op_success=op_success,
                exec_state=exec_state,
                backup_too_small=backup_too_small,
            )
            if not result:
                logger.error(
                    f"Failed to send email notification to {recipient} for {operation} {'success' if op_success else 'failure'}."
                )

    def _send_email(
        self,
        smtp_server: str,
        smtp_port: int,
        smtp_security: str,
        smtp_username: Optional[str],
        smtp_password: Optional[str],
        sender: str,
        recipients: List[str],
        instance: str,
        operation: str,
        metrics: Dict[str, Any],
        labels: Dict[str, str],
        op_success: bool,
        exec_state: int,
        backup_too_small: bool,
    ) -> bool:
        """
        Build and send email notification

        Args:
            smtp_server: SMTP server hostname
            smtp_port: SMTP server port
            smtp_security: Security mode (tls, ssl, none)
            smtp_username: Optional SMTP username
            smtp_password: Optional SMTP password
            sender: Sender email address
            recipients: Comma-separated recipient addresses
            instance: Instance identifier
            operation: Operation name
            metrics: Dictionary of metrics
            labels: Dictionary of labels
            op_success: Whether operation was successful
            exec_state: Execution state (0-3)
            backup_too_small: Whether backup was too small

        Returns:
            True if successful, False otherwise
        """
        repo_name = labels.get("repo_name", "unknown")

        logger.info(f"Sending metrics via email to {recipients}.")

        mailer = Mailer(
            smtp_server=smtp_server,
            smtp_port=smtp_port,
            security=smtp_security,
            smtp_user=smtp_username,
            smtp_password=smtp_password,
            debug=False,  # Make sure we don't send debug info so we don't leak passwords
        )

        # Build subject
        if op_success:
            subject = f"{OEM_STRING} success report for {instance} {operation} on repo {repo_name}"
        else:
            subject = f"{OEM_STRING} failure report for {instance} {operation} on repo {repo_name}"

        # Build body
        body = f"Operation: {operation}\nRepo: {repo_name}"

        if op_success:
            body += "\nStatus: Success"
        elif backup_too_small:
            body += "\nStatus: Backup too small"
        elif exec_state == 1:
            body += "\nStatus: Warning"
        elif exec_state == 2:
            body += "\nStatus: Error"
        elif exec_state == 3:
            body += "\nStatus: Critical error"

        # Add timestamp
        from datetime import datetime, timezone

        date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        body += f"\nDate: {date}"

        # Add execution time if available
        if "exec_time" in metrics:
            body += f"\nExecution time: {metrics['exec_time']:.2f} seconds"

        # Add detailed metrics for backup operations
        if operation == "backup":
            if "total_bytes_processed" in metrics:
                bytes_val = metrics["total_bytes_processed"]
                if bytes_val:
                    if bytes_val >= 1024**3:  # GB
                        body += f"\nData processed: {bytes_val / (1024**3):.2f} GB"
                    elif bytes_val >= 1024**2:  # MB
                        body += f"\nData processed: {bytes_val / (1024**2):.2f} MB"
                    else:  # KB
                        body += f"\nData processed: {bytes_val / 1024:.2f} KB"

            if "files_new" in metrics:
                body += f"\nNew files: {metrics['files_new']}"
            if "files_changed" in metrics:
                body += f"\nChanged files: {metrics['files_changed']}"
            if "files_unmodified" in metrics:
                body += f"\nUnmodified files: {metrics['files_unmodified']}"

        # Add detailed result if available (for debugging)
        # Note: This is optional and may contain raw restic output
        # We'll look for it in a special key if the caller wants to include it
        if "result_detail" in metrics:
            restic_result = metrics["result_detail"]
            if isinstance(restic_result, dict):
                try:
                    restic_result = fmt_json(restic_result)
                except TypeError:
                    # TypeError may happen on ls command which contains a json of LSNodes
                    pass

            # Convert to string and truncate if needed
            restic_result = str(restic_result)
            if len(restic_result) > MAX_EMAIL_DETAIL_LENGTH:
                body += f"\n\nDetail:\n{restic_result[0:MAX_EMAIL_DETAIL_LENGTH]} [... truncated]"
            else:
                body += f'\n\nDetail:\n{"Backend success" if restic_result else "Backend failure"}'

        body += f"\n\nLabels:"
        for label, value in labels.items():
            body += f"\n{label}: {value}"

        body += f"\n\nGenerated by {OEM_STRING} {version_dict['version']}\n"

        try:
            result = mailer.send_email(
                sender_mail=sender,
                recipient_mails=recipients,
                subject=subject,
                body=body,
            )
            if result:
                logger.info("Metrics sent via email.")
                return True
        except Exception as exc:
            logger.error(f"Failed to send metrics via email: {exc}")
            logger.debug("Trace:", exc_info=True)

        return False
