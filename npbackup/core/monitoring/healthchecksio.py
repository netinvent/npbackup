#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.core.monitoring.healthchecksio"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2026 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2025112601"

from typing import Dict, Any, Optional
from logging import getLogger
import requests
from npbackup.core.monitoring import MonitoringBackend

logger = getLogger()


class HealthchecksioMonitor(MonitoringBackend):
    """
    Healthchecks.io monitoring backend implementation
    Uses simple HTTP ping endpoints to signal job status
    """

    def __init__(self, repo_config: dict, monitoring_config: dict):
        """
        Initialize Healthchecks.io monitoring backend

        Args:
            repo_config: Repository configuration dictionary
        """
        super().__init__(repo_config, monitoring_config)

    def is_enabled(self) -> bool:
        return self.get_monitoring_value("global_healthchecksio.enabled", False)

    def _get_params(self) -> None:
        self.url = self.get_monitoring_value("global_healthchecksio.url")
        if not self.url:
            logger.error("Healthchecks.io URL not configured.")
            return False

        # Get timeout from config, default to 10 seconds
        self.timeout = self.get_monitoring_value("global_healthchecksio.timeout", 10)

        self.verify = not self.get_monitoring_value(
            "global_healthchecksio.no_cert_verify", False
        )

    def send_metrics(
        self,
        metrics: Dict[str, Any],
        operation: str,
        dry_run: bool = False,
    ) -> bool:
        """
        Send status ping to Healthchecks.io

        Healthchecks.io uses a simple ping model:
        - Ping base URL on success
        - Ping /fail endpoint on failure
        - Optionally send log data in request body

        Args:
            metrics: Dictionary of metric names and values
            labels: Dictionary of labels/tags for the metrics
            operation: Operation name (backup, restore, etc.)
            dry_run: If True, don't actually send ping

        Returns:
            True if successful, False otherwise
        """
        if not self.is_enabled():
            logger.debug("Healthchecks.io monitoring not enabled in configuration.")
            return False

        # Determine if operation was successful
        exec_state = metrics.get("npbackup_exec_state", 0)
        operation_success = metrics.get("operation_success", 1)

        # exec_state: 0=success, 1=warning, 2=error, 3=critical
        # Consider warnings as success for healthchecks.io
        is_success = exec_state in (0, 1) and operation_success == 1

        # Build log data to send with ping
        log_data = self._build_log_data(metrics, operation)

        if dry_run:
            logger.info("Dry run mode. Not sending Healthchecks.io ping.")
            return True

        # Send the ping
        return self._send_ping(is_success, log_data)

    def _build_log_data(self, metrics: Dict[str, Any], operation: str) -> str:
        """
        Build log data to send with the ping

        Args:
            metrics: Dictionary of metrics
            labels: Dictionary of labels
            operation: Operation name

        Returns:
            Formatted log data string
        """
        labels = self.common_labels
        lines = []
        lines.append(f"Operation: {operation}")
        lines.append(f"Repository: {labels.get('repo_name', 'unknown')}")

        exec_state = metrics.get("npbackup_exec_state", 0)
        state_names = {0: "Success", 1: "Warning", 2: "Error", 3: "Critical"}
        lines.append(f"Status: {state_names.get(exec_state, 'Unknown')}")

        if "npbackup_exec_time" in metrics:
            lines.append(f"Execution time: {metrics['npbackup_exec_time']:.2f}s")

        # Add backup-specific metrics if available
        if operation == "backup":
            if "restic_total_bytes_processed" in metrics:
                # Convert bytes to human-readable format
                bytes_val = metrics["restic_total_bytes_processed"]
                if bytes_val:
                    if bytes_val >= 1024**3:  # GB
                        lines.append(f"Data processed: {bytes_val / (1024**3):.2f} GB")
                    elif bytes_val >= 1024**2:  # MB
                        lines.append(f"Data processed: {bytes_val / (1024**2):.2f} MB")
                    else:  # KB
                        lines.append(f"Data processed: {bytes_val / 1024:.2f} KB")

            if "restic_files" in metrics:
                lines.append(f"New files: {metrics['restic_files']['new']}")
                lines.append(f"Changed files: {metrics['restic_files']['changed']}")
                lines.append(
                    f"Unmodified files: {metrics['restic_files']['unmodified']}"
                )
                lines.append(f"Total files: {metrics['restic_files']['total']}")
            if "restic_dirs" in metrics:
                lines.append(f"New directories: {metrics['restic_dirs']['new']}")
                lines.append(
                    f"Changed directories: {metrics['restic_dirs']['changed']}"
                )
                lines.append(
                    f"Unmodified directories: {metrics['restic_dirs']['unmodified']}"
                )

        return "\n".join(lines)

    def _send_ping(self, is_success: bool, log_data: Optional[str] = None) -> bool:
        """
        Send ping to Healthchecks.io

        Args:
            is_success: Whether the operation was successful
            log_data: Optional log data to send with the ping

        Returns:
            True if ping was sent successfully, False otherwise
        """
        self._get_params()
        try:
            # Build the ping URL
            if is_success:
                ping_endpoint = self.url
            else:
                # Append /fail for failures
                ping_endpoint = f"{self.url.rstrip('/')}/fail"

            # Send the ping
            if log_data:
                response = requests.post(
                    ping_endpoint,
                    data=log_data.encode("utf-8"),
                    timeout=self.timeout,
                    verify=self.verify,
                )
            else:
                response = requests.get(
                    ping_endpoint, verify=self.verify, timeout=self.timeout
                )

            if response.status_code == 200:
                status = "success" if is_success else "failure"
                logger.info(f"Successfully sent Healthchecks.io {status} ping")
                return True
            else:
                logger.warning(
                    f"Healthchecks.io ping returned status {response.status_code}: {response.text}"
                )
                return False

        except requests.RequestException as exc:
            logger.error(f"Failed to send Healthchecks.io ping: {exc}")
            logger.debug("Trace:", exc_info=True)
            return False
        except Exception as exc:
            logger.error(f"Unexpected error sending Healthchecks.io ping: {exc}")
            logger.debug("Trace:", exc_info=True)
            return False

    def send_start_ping(self) -> bool:
        """
        Send a start ping to Healthchecks.io (optional)
        This signals that a job has started

        Returns:
            True if ping was sent successfully, False otherwise
        """
        if not self.is_enabled() or not self.url:
            return False
        self._get_params()
        try:
            start_endpoint = f"{self.url.rstrip('/')}/start"

            response = requests.get(
                start_endpoint, verify=self.verify, timeout=self.timeout
            )

            if response.status_code == 200:
                logger.debug("Sent Healthchecks.io start ping")
                return True
            else:
                logger.debug(
                    f"Healthchecks.io start ping returned status {response.status_code}"
                )
                return False
        except Exception as exc:
            logger.debug(f"Failed to send Healthchecks.io start ping: {exc}")
            return False
