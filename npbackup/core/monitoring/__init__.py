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
from copy import deepcopy
from typing import Optional, Dict, List, Any
from datetime import datetime, timezone
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
        self.metrics_timestamp = int(datetime.now(timezone.utc).timestamp())
        self.repo_config = repo_config
        self.monitoring_config = monitoring_config
        self.logger = logger
        self._common_labels = {
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
                if k not in self._common_labels:
                    self._common_labels[k] = v

        # Enhance labels with npbackup version info
        if "npversion" not in self._common_labels:
            self._common_labels["npversion"] = (
                f"{NAME}{version_dict['version']}-{version_dict['build_type']}"
            )
        if "audience" not in self._common_labels:
            self._common_labels["audience"] = version_dict.get("audience", "unknown")
        if "os" not in self._common_labels:
            self._common_labels["os"] = version_dict.get("os", "unknown")
        if "arch" not in self._common_labels:
            self._common_labels["arch"] = version_dict.get("arch", "unknown")

    @property
    def common_labels(self) -> Dict[str, str]:
        return self._common_labels

    @common_labels.setter
    def common_labels(self, labels: Dict[str, str]):
        self._common_labels = {**self._common_labels, **labels}

    @abstractmethod
    def send_metrics(
        self,
        metrics: Dict[str, Any],
        operation: str,
        dry_run: bool = False,
    ) -> bool:
        """
        Send metrics to the monitoring backend

        Args:
            metrics: Dictionary of metric names and values
            common_labels: Dictionary of labels/tags for the metrics
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

    def build_json_output(
        self,
        metrics: Dict[str, Any],
        operation: str,
    ) -> dict:

        # Avoid mutating original metrics dict
        metrics = deepcopy(metrics)
        output = []
        if "npbackup_upgrade_state" in metrics.keys():
            metrics["npbackup_exec_state"] = metrics["npbackup_upgrade_state"]
            output.append(
                {
                    "result": metrics["npbackup_upgrade_state"],
                    "operation": "upgrade",
                    "metrics": [
                        metrics["npbackup_exec_state"],
                        metrics["npbackup_exec_time"],
                    ],
                    "timestamp": self.metrics_timestamp,
                    "labels": self.common_labels,
                }
            )
            del metrics["npbackup_upgrade_state"]

        output.append(
            {
                "result": metrics["npbackup_exec_state"],
                "operation": operation,
                "metrics": metrics,
                "timestamp": self.metrics_timestamp,
                "labels": self.common_labels,
            }
        )
        return output

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
        except AssertionError:
            logger.debug(
                f"Key {key} not found in monitoring configuration, returning default."
            )
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
        except AssertionError:
            logger.debug(f"Key {key} not found in configuration, returning default.")
            return default


def calculate_exec_state(
    operation_success: bool,
    worst_logger_level: int,
) -> int:
    """
    Calculate execution state from operation results

    Args:
        operation_success: Whether the operation succeeded
        worst_logger_level: Worst log level encountered (50=CRITICAL, 40=ERROR, 30=WARNING, 20=INFO)

    Returns:
        exec_state: 0=success, 1=warning, 2=error, 3=critical, 4=unknown

        Note: exec_state=4 is not used as of today
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
    if not operation_success and exec_state < 3:
        exec_state = 2

    return exec_state
