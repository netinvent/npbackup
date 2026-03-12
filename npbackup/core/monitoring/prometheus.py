#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.core.monitoring.prometheus"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2026 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2025112601"

from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from logging import getLogger
from npbackup.core.monitoring import MonitoringBackend
from npbackup.restic_metrics import (
    upload_metrics,
    write_metrics_file,
)
from npbackup.__version__ import __intname__

logger = getLogger()


class PrometheusMonitor(MonitoringBackend):
    """
    Prometheus monitoring backend implementation
    """

    def __init__(
        self, repo_config: dict, monitoring_config: dict, append_mode: bool = False
    ):
        """
        Initialize Prometheus monitoring backend

        Args:
            repo_config: Repository configuration dictionary
            append_mode: Whether to append to metrics file instead of overwriting, useful for group runner
        """
        super().__init__(repo_config, monitoring_config)
        self.append_mode = append_mode

    def is_enabled(self) -> bool:
        return self.get_monitoring_value("global_prometheus.enabled", False)

    def send_metrics(
        self,
        metrics: Dict[str, Any],
        operation: str,
        dry_run: bool = False,
    ) -> bool:
        """
        Send metrics to Prometheus pushgateway or write to file

        Args:
            metrics: Dictionary of metric names and values
            labels: Dictionary of labels for the metrics
            operation: Operation name (backup, restore, etc.)
            dry_run: If True, don't actually send metrics

        Returns:
            True if successful, False otherwise
        """
        if not self.is_enabled():
            logger.debug("Prometheus metrics not enabled in configuration.")
            return False

        # Get Prometheus-specific configuration
        try:
            # Try new config structure first, fall back to old
            destination = self.get_monitoring_value("global_prometheus.destination")
            no_cert_verify = self.get_monitoring_value(
                "global_prometheus.no_cert_verify", False
            )
        except (KeyError, AttributeError) as exc:
            logger.error(f"No Prometheus configuration found: {exc}")
            return False

        # Convert metrics dict to Prometheus format
        prom_metrics = self._convert_to_prometheus_format(metrics)

        if not destination:
            logger.debug("No Prometheus destination set. Not sending metrics")
            return True

        if dry_run:
            logger.info("Dry run mode. Not sending metrics.")
            return True

        logger.debug(f"Sending metrics to {destination}")
        dest = destination.lower()

        if dest.startswith("http"):
            return self._upload_to_pushgateway(
                destination, no_cert_verify, prom_metrics, operation
            )
        else:
            return self._write_to_file(destination, prom_metrics)

    def _convert_to_prometheus_format(self, metrics: Dict[str, Any]) -> List[str]:
        """
        Convert metrics dictionary to Prometheus text format
        """
        prom_metrics = []
        # Add timestamp to npbackup labels only
        npbackup_labels = {"timestamp": self.metrics_timestamp, **self._common_labels}

        # Convert common metrics to Prometheus format
        for metric_name, value in metrics.items():
            if value is None:
                continue

            if metric_name.startswith("npbackup_"):
                # Patch upgrade state into npbackup_exec_state{action="upgrade")}
                if metric_name == "npbackup_upgrade_state":
                    prom_metrics.append(
                        f'npbackup_exec_state{{{self.create_labels_string({**npbackup_labels, "action": "upgrade"})}}} {value}'
                    )
                else:
                    prom_metrics.append(
                        f"{metric_name}{{{self.create_labels_string(npbackup_labels)}}} {value}"
                    )
            elif metric_name.startswith("restic_"):
                if isinstance(value, dict):
                    for sub_metric, sub_value in value.items():
                        if sub_value is None:
                            continue
                        prom_metrics.append(
                            f'{metric_name}{{{self.create_labels_string({**self.common_labels, "state": sub_metric})}}} {sub_value}'
                        )
                else:
                    prom_metrics.append(
                        f"{metric_name}{{{self.create_labels_string(self.common_labels)}}} {value}"
                    )
            else:
                logger.error(
                    f"Unknown metric {metric_name} with value {value}, skipping."
                )

        logger.debug("Prometheus metrics computed:\n{}".format("\n".join(prom_metrics)))
        return prom_metrics

    def _upload_to_pushgateway(
        self,
        destination: str,
        no_cert_verify: bool,
        metrics: List[str],
        operation: str,
    ) -> bool:
        """
        Upload metrics to Prometheus pushgateway

        Args:
            destination: Pushgateway URL
            no_cert_verify: Whether to skip SSL certificate verification
            metrics: List of Prometheus-formatted metrics
            operation: Operation name

        Returns:
            True if successful, False otherwise
        """
        if "metrics" not in destination.lower():
            logger.error(
                "Destination does not contain 'metrics' keyword. Not uploading."
            )
            return False
        if "job" not in destination.lower():
            logger.error("Destination does not contain 'job' keyword. Not uploading.")
            return False

        try:
            # Try new config structure first, fall back to old
            authentication = (
                self.get_monitoring_value("global_prometheus.http_username"),
                self.get_monitoring_value("global_prometheus.http_password"),
            )
        except (KeyError, AttributeError):
            logger.info("No Prometheus authentication present.")
            authentication = None

        # Fix for #150: Make job name unique per repo and operation
        repo_name = self.get_config_value("name")
        destination = f"{destination}___repo_name={repo_name}___action={operation}"
        result = upload_metrics(destination, authentication, no_cert_verify, metrics)
        return result

    def _write_to_file(self, destination: str, metrics: List[str]) -> bool:
        """
        Write metrics to file for node_exporter text collector

        Args:
            destination: File path
            metrics: List of Prometheus-formatted metrics

        Returns:
            True if successful, False otherwise
        """
        result = write_metrics_file(destination, metrics, append=self.append_mode)
        return result

    @staticmethod
    def create_labels_string(labels: dict) -> str:
        """
        Create a string with labels for prometheus metrics
        """
        _labels = []
        for key, value in sorted(labels.items()):
            if value:
                _labels.append(f'{str(key).strip()}="{str(value).strip()}"')
        labels_string = ",".join(sorted(list(set(_labels))))
        return labels_string
