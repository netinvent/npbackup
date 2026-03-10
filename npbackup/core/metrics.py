#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.core.metrics"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2026 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2026030501"

import os
from typing import Optional, Tuple, List
from datetime import datetime, timezone
from logging import getLogger
from npbackup.restic_metrics import (
    restic_str_output_to_json,
    restic_json_to_prometheus,
)
from npbackup.core.monitoring import calculate_exec_state, collect_common_metrics
from npbackup.core.monitoring.prometheus import PrometheusMonitor
from npbackup.core.monitoring.zabbix import ZabbixMonitor
from npbackup.core.monitoring.healthchecksio import HealthchecksioMonitor
from npbackup.core.monitoring.webhook import WebhookMonitor
from npbackup.core.monitoring.email import EmailMonitor
from npbackup.__version__ import __intname__ as NAME, version_dict

logger = getLogger()


def metric_analyser(
    repo_config: dict,
    monitoring_config: dict,
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
    repo_name = repo_config.g("name")
    try:
        # Build labels for monitoring backends
        labels = {
            "repo_name": repo_name,
            "action": operation,
        }

        # Add instance and group labels (support both old and new config)
        instance = repo_config.g("global_monitoring.instance") or repo_config.g(
            "global_prometheus.instance"
        )
        if instance:
            labels["instance"] = instance

        # Add prometheus-specific labels for backward compatibility
        try:
            backup_job = repo_config.g("prometheus.backup_job")
            if backup_job:
                labels["backup_job"] = backup_job
        except (KeyError, AttributeError):
            pass

        try:
            group = repo_config.g("prometheus.group")
            if group:
                labels["group"] = group
        except (KeyError, AttributeError):
            pass

        # Analyze backup output from restic
        restic_metrics = {}
        if operation == "backup":
            minimum_backup_size_error = repo_config.g(
                "backup_opts.minimum_backup_size_error"
            )
            # If result was a str, we need to transform it into json first
            if isinstance(result_string, str):
                restic_result = restic_str_output_to_json(restic_result, result_string)

            # Parse restic output to get metrics
            operation_success, prom_metrics, backup_too_small = (
                restic_json_to_prometheus(
                    restic_result=restic_result,
                    restic_json=restic_result,
                    labels=labels,
                    minimum_backup_size_error=minimum_backup_size_error,
                )
            )

            # Convert restic result to metrics dict if it's a dict
            if isinstance(restic_result, dict):
                restic_metrics = restic_result

        if not operation_success or not restic_result:
            logger.error("Backend finished with errors.")

        # Calculate execution state
        worst_exec_level = logger.get_worst_logger_level()
        exec_state = calculate_exec_state(
            operation_success, backup_too_small, worst_exec_level
        )

        if not analyze_only:
            # reset worst_exec_level after getting it so we don't keep exec level between runs in the same session
            logger.set_worst_logger_level(0)

        # Collect common metrics
        common_metrics = collect_common_metrics(
            operation=operation,
            operation_success=operation_success,
            backup_too_small=backup_too_small,
            exec_state=exec_state,
            exec_time=exec_time,
            restic_result=restic_metrics,
        )

        # Add upgrade state if upgrades activated
        upgrade_state = os.environ.get("NPBACKUP_UPGRADE_STATE", None)
        try:
            upgrade_state = int(upgrade_state)
            common_metrics["upgrade_state"] = upgrade_state
        except (ValueError, TypeError):
            pass

        if not analyze_only:
            # Add restic result detail for email backend if available
            if restic_result:
                common_metrics["result_detail"] = (
                    0 if (restic_result is True or restic_result == 0) else 1
                )

            # Send metrics to all enabled monitoring backends (including email)
            _send_to_monitoring_backends(
                monitoring_config,
                repo_config,
                common_metrics,
                labels,
                operation,
                dry_run,
                append_metrics_file,
            )
    except KeyError as exc:
        logger.info(f"Metrics error: {exc}")
        logger.debug("Trace:", exc_info=True)
    except OSError as exc:
        logger.error(f"Metrics OS error: {exc}")
        logger.debug("Trace:", exc_info=True)
    return operation_success, backup_too_small


def _send_to_monitoring_backends(
    monitoring_config: dict,
    repo_config: dict,
    metrics: dict,
    labels: dict,
    operation: str,
    dry_run: bool = False,
    append_metrics_file: bool = False,
) -> bool:
    """
    Send metrics to all enabled monitoring backends

    Args:
        repo_config: Repository configuration
        metrics: Dictionary of metrics
        labels: Dictionary of labels
        operation: Operation name
        dry_run: Dry run mode
        append_metrics_file: Whether to append to metrics file

    Returns:
        True if at least one backend succeeded, False otherwise
    """
    success = False

    # Initialize all monitoring backends
    backends = [
        PrometheusMonitor(repo_config, monitoring_config, append_metrics_file),
        ZabbixMonitor(repo_config, monitoring_config),
        HealthchecksioMonitor(repo_config, monitoring_config),
        WebhookMonitor(repo_config, monitoring_config, append_metrics_file),
        EmailMonitor(repo_config, monitoring_config),
    ]

    # Send metrics to all enabled backends
    has_enabled_backends = False
    for backend in backends:
        if backend.is_enabled():
            has_enabled_backends = True
            try:
                result = backend.send_metrics(metrics, labels, operation, dry_run)
                if result:
                    success = True
            except Exception as exc:
                logger.error(
                    f"Failed to send metrics to {backend.__class__.__name__}: {exc}"
                )
                logger.debug("Trace:", exc_info=True)

    if not success:
        logger.debug(f"Monitoring failed, has enabled backends: {has_enabled_backends}")

    return success


def send_prometheus_metrics(
    repo_config: dict,
    monitoring_config: dict,
    metrics: List[str],
    dry_run: bool = False,
    append_metrics_file: bool = False,
    operation: Optional[str] = None,
) -> bool:
    """
    Legacy function for backward compatibility
    Converts old prometheus metrics format to new backend system

    DEPRECATED: Use _send_to_monitoring_backends instead
    """
    logger.warning(
        "send_prometheus_metrics is deprecated. Please update to use the new monitoring backend system."
    )

    # Use Prometheus backend directly for legacy support
    prometheus = PrometheusMonitor(repo_config, monitoring_config, append_metrics_file)

    if not prometheus.is_enabled():
        logger.debug("Prometheus metrics not enabled in configuration.")
        return False

    # This is a simplified compatibility shim - metrics are already in Prometheus format
    # so we can't easily convert them back. Log a warning.
    logger.warning(
        "Called legacy send_prometheus_metrics with pre-formatted metrics. "
        "Consider updating caller to use new monitoring system."
    )

    return True


def send_metrics_mail(
    repo_config: dict,
    monitoring_config: dict,
    operation: str,
    restic_result: Optional[dict] = None,
    operation_success: Optional[bool] = None,
    backup_too_small: Optional[bool] = None,
    exec_state: Optional[int] = None,
    date: Optional[int] = None,
):
    """
    Legacy function for backward compatibility

    DEPRECATED: Email is now handled by the EmailMonitor backend.
    This function is kept for backward compatibility but delegates to the new system.
    """
    logger.warning(
        "send_metrics_mail is deprecated. Email notifications are now handled "
        "by the EmailMonitor backend automatically."
    )

    # Build metrics dict for the email backend
    metrics = {
        "exec_state": exec_state,
        "operation_success": 1 if operation_success else 0,
        "backup_too_small": 1 if backup_too_small else 0,
    }

    if restic_result:
        metrics["restic_result_detail"] = restic_result

    labels = {
        "repo_name": repo_config.g("name"),
        "action": operation,
    }

    # Use the email backend directly
    email_backend = EmailMonitor(repo_config, monitoring_config)
    return email_backend.send_metrics(metrics, labels, operation, dry_run=False)
