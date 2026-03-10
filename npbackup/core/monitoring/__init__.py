#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.core.monitoring"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2026 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2025112601"

from abc import ABC, abstractmethod
from typing import Optional, Dict, List, Any
from logging import getLogger
from npbackup.__version__ import __intname__ as NAME, version_dict

logger = getLogger()


class MonitoringBackend(ABC):
    """
    Abstract base class for monitoring backends
    """

    def __init__(self, repo_config: dict, monitoring_config: dict):
        """
        Initialize monitoring backend with repository configuration

        Args:
            monitoring_config: Monitoring configuration dictionary
            repo_config: Repository configuration dictionary
        """
        self.repo_config = repo_config
        self.monitoring_config = monitoring_config
        self.logger = logger
        self.base_labels = {
            "instance": self.get_config_value(
                "monitoring.instance", "default_instance"
            ),
            "group": self.get_config_value("monitoring.group", "default_group"),
            "backup_job": self.get_config_value(
                "monitoring.backup_job", "default_backup_job"
            ),
        }
        # Add additional labels from config
        additional_labels = self.get_config_value("monitoring.additional_labels")
        if isinstance(additional_labels, dict):
            for k, v in additional_labels.items():
                if k not in self.base_labels:
                    self.base_labels[k] = v

        # Enhance labels with npbackup version info
        if "npversion" not in self.base_labels:
            self.base_labels["npversion"] = (
                f"{NAME}{version_dict['version']}-{version_dict['build_type']}"
            )
        if "audience" not in self.base_labels:
            self.base_labels["audience"] = version_dict.get("audience", "unknown")
        if "os" not in self.base_labels:
            self.base_labels["os"] = version_dict.get("os", "unknown")
        if "arch" not in self.base_labels:
            self.base_labels["arch"] = version_dict.get("arch", "unknown")

    @abstractmethod
    def send_metrics(
        self,
        metrics: Dict[str, Any],
        labels: Dict[str, str],
        operation: str,
        dry_run: bool = False,
    ) -> bool:
        """
        Send metrics to the monitoring backend

        Args:
            metrics: Dictionary of metric names and values
            labels: Dictionary of labels/tags for the metrics
            operation: Operation name (backup, restore, etc.)
            dry_run: If True, don't actually send metrics

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    def is_enabled(self) -> bool:
        """
        Check if this monitoring backend is enabled in configuration

        Returns:
            True if enabled, False otherwise
        """
        pass

    def get_monitoring_value(self, key: str, default: Any = None) -> Any:
        """
        Helper method to get monitoring configuration values

        Args:
            key: Configuration key (supports dot notation)
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        try:
            value = self.monitoring_config.g(key)
            if value is not None:
                return value
            return default
        except (KeyError, AttributeError):
            return default

    def get_config_value(self, key: str, default: Any = None) -> Any:
        """
        Helper method to get configuration values

        Args:
            key: Configuration key (supports dot notation)
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        try:
            value = self.repo_config.g(key)
            if value is not None:
                return value
            return default
        except (KeyError, AttributeError):
            return default


def calculate_exec_state(
    operation_success: bool,
    backup_too_small: bool,
    worst_logger_level: int,
) -> int:
    """
    Calculate execution state from operation results

    Args:
        operation_success: Whether the operation succeeded
        backup_too_small: Whether backup was too small
        worst_logger_level: Worst log level encountered (50=CRITICAL, 40=ERROR, 30=WARNING, 20=INFO)

    Returns:
        exec_state: 0=success, 1=warning, 2=error, 3=critical
    """
    # Map logger levels to exec states
    if worst_logger_level == 50:  # CRITICAL
        exec_state = 3
    elif worst_logger_level == 40:  # ERROR
        exec_state = 2
    elif worst_logger_level == 30:  # WARNING
        exec_state = 1
    else:
        exec_state = 0

    # Override with operation-specific failures
    if not operation_success or backup_too_small:
        exec_state = 2

    return exec_state


def collect_common_metrics(
    operation: str,
    operation_success: bool,
    backup_too_small: bool,
    exec_state: int,
    exec_time: Optional[float] = None,
    restic_result: Optional[dict] = None,
) -> Dict[str, Any]:
    """
    Collect common metrics that apply to all monitoring backends

    Args:
        operation: Operation name (backup, restore, etc.)
        operation_success: Whether operation succeeded
        backup_too_small: Whether backup was too small
        exec_state: Execution state (0-3)
        exec_time: Execution time in seconds
        restic_result: Restic result dictionary (for backup operations)

    Returns:
        Dictionary of common metrics
    """
    metrics = {
        "operation": operation,
        "exec_state": exec_state,
        "operation_success": 1 if operation_success else 0,
        "backup_too_small": 1 if backup_too_small else 0,
    }

    if exec_time is not None:
        metrics["exec_time"] = exec_time

    # Add restic-specific metrics if available
    if restic_result and isinstance(restic_result, dict):
        for key in [
            "files_new",
            "files_changed",
            "files_unmodified",
            "dirs_new",
            "dirs_changed",
            "dirs_unmodified",
            "data_added",
            "total_files_processed",
            "total_bytes_processed",
            "total_duration",
        ]:
            if key in restic_result and restic_result[key] is not None:
                metrics[key] = restic_result[key]

    return metrics
