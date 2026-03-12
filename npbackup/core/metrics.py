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
from ofunctions.misc import BytesConverter
from npbackup.restic_metrics import (
    restic_str_output_to_json,
    restic_json_to_prometheus,
)
from npbackup.core.monitoring import calculate_exec_state
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
    only_check_backup_result_and_size: bool = False,
) -> Tuple[bool, bool]:
    """
    Tries to get operation success and backup to small booleans from restic output
    Returns op success, backup too small
    """
    operation_success = True
    backup_too_small = False
    repo_name = repo_config.g("name")
    # Build labels for monitoring backends
    common_labels = {
        "repo_name": repo_name,
        "action": operation,
    }

    try:

        metrics = {}
        if operation == "backup":
            minimum_backup_size_error = repo_config.g(
                "backup_opts.minimum_backup_size_error"
            )
            # If result was a str, we need to transform it into json first
            # Currently, @metrics uses str instead of json in order to detect cloud file issues
            # see @metrics for more
            if result_string is None:
                restic_json = {}
            if isinstance(result_string, str):
                restic_json = restic_str_output_to_json(restic_result, result_string)

            backup_too_small = False
            if restic_json:
                try:
                    if restic_json["total_bytes_processed"]:
                        # We need human iec bytes for normalization across other values
                        processed_bytes_iec = BytesConverter(
                            str(restic_json["total_bytes_processed"])
                        ).human_iec_bytes
                        logger.info(f"Processed {processed_bytes_iec} of data")
                        if minimum_backup_size_error:
                            # We need bytes for literal comparison
                            processed_bytes = BytesConverter(
                                str(restic_json["total_bytes_processed"])
                            ).bytes
                            if processed_bytes < int(
                                BytesConverter(
                                    str(minimum_backup_size_error).replace(" ", "")
                                ).bytes
                            ):
                                backup_too_small = True
                except Exception as exc:
                    logger.warning(f"Cannot determine processed bytes: {exc}")
                    logger.debug("Trace:", exc_info=True)
                    # We don't care if this exception happens, as error state still will raise from
                    # other parts of this code
            else:
                logger.error("Backup operation did not return valid parseable data")

            if only_check_backup_result_and_size:
                return restic_result, backup_too_small

            metrics["restic_backup_failure"] = (
                0 if (restic_result and not backup_too_small) else 1
            )

            # Add generic restic metrics
            metrics["restic_files"] = {}
            metrics["restic_dirs"] = {}
            for key, value in restic_json.items():
                # Compat with v3.0.x versions whre we used to have restic_total_duration_seconds
                if key == "total_duration":
                    key = "total_duration_seconds"
                if key.startswith("files_") or key.startswith("dirs_"):
                    category = key.split("_")[0]
                    state = key.split("_")[-1]
                    metrics[f"restic_{category}"][state] = int(value)
                else:
                    try:
                        metrics[f"restic_{key}"] = int(value)
                    except (ValueError, TypeError):
                        metrics[f"restic_{key}"] = value

        if not operation_success or not restic_result:
            logger.error("Backend finished with errors.")

        # Calculate execution state
        worst_exec_level = logger.get_worst_logger_level()
        exec_state = calculate_exec_state(
            operation_success, backup_too_small, worst_exec_level
        )
        metrics["npbackup_exec_state"] = exec_state
        metrics["npbackup_exec_time"] = exec_time

        # Add upgrade state if upgrades activated
        upgrade_state = os.environ.get("NPBACKUP_UPGRADE_STATE", None)
        try:
            upgrade_state = int(
                upgrade_state
            )  # We cannot double use npbackup_exec_state for upgrade and other actions
            metrics["npbackup_upgrade_state"] = upgrade_state
        except (ValueError, TypeError):
            pass

        if not only_check_backup_result_and_size:
            # reset worst_exec_level after getting it so we don't keep exec level between runs in the same session
            logger.set_worst_logger_level(0)
            # Send metrics to all enabled monitoring backends (including email)
            _send_to_monitoring_backends(
                monitoring_config,
                repo_config,
                metrics,
                common_labels,
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
    common_labels: dict,
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
            backend.common_labels = common_labels
            has_enabled_backends = True
            try:
                result = backend.send_metrics(metrics, operation, dry_run)
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
