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
    create_labels_string,
    upload_metrics,
    write_metrics_file,
)
from npbackup.__version__ import __intname__ as NAME, version_dict

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
        print("MON")
        print(monitoring_config)
        self.append_mode = append_mode

    def is_enabled(self) -> bool:
        return self.get_monitoring_value("global_prometheus.enabled", False)

    def send_metrics(
        self,
        metrics: Dict[str, Any],
        labels: Dict[str, str],
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
            print("DES", destination)
            no_cert_verify = self.get_monitoring_value(
                "global_prometheus.no_cert_verify", False
            )
        except (KeyError, AttributeError) as exc:
            logger.error(f"No Prometheus configuration found: {exc}")
            return False

        # Convert metrics dict to Prometheus format
        prom_metrics = self._convert_to_prometheus_format(metrics, labels)

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

    def _convert_to_prometheus_format(
        self, metrics: Dict[str, Any], labels: Dict[str, str]
    ) -> List[str]:
        """
        Convert metrics dictionary to Prometheus text format

        Args:
            metrics: Dictionary of metrics
            labels: Dictionary of labels

        Returns:
            List of Prometheus-formatted metric strings
        """
        # Enhance labels with npbackup version info
        enhanced_labels = labels.copy()
        if "npversion" not in enhanced_labels:
            enhanced_labels["npversion"] = (
                f"{NAME}{version_dict['version']}-{version_dict['build_type']}"
            )
        if "audience" not in enhanced_labels:
            enhanced_labels["audience"] = version_dict.get("audience", "unknown")
        if "os" not in enhanced_labels:
            enhanced_labels["os"] = version_dict.get("os", "unknown")
        if "arch" not in enhanced_labels:
            enhanced_labels["arch"] = version_dict.get("arch", "unknown")

        # Add Prometheus-specific labels from config
        additional_labels = self.get_config_value("monitoring.additional_labels")
        if isinstance(additional_labels, dict):
            for k, v in additional_labels.items():
                enhanced_labels[k] = v

        labels_string = create_labels_string(enhanced_labels)
        timestamp = int(datetime.now(timezone.utc).timestamp())
        prom_metrics = []

        # Convert common metrics to Prometheus format
        for metric_name, value in metrics.items():
            if value is None:
                continue

            # Special handling for certain metrics
            if metric_name == "operation":
                continue  # Operation is already in labels
            elif metric_name == "exec_state":
                prom_metrics.append(
                    f'npbackup_exec_state{{{labels_string},timestamp="{timestamp}"}} {value}'
                )
            elif metric_name == "exec_time":
                prom_metrics.append(
                    f'npbackup_exec_time{{{labels_string},timestamp="{timestamp}"}} {value}'
                )
            elif metric_name in ["operation_success", "backup_too_small"]:
                # These are already captured in exec_state
                continue
            else:
                # Restic-specific metrics
                if "files" in metric_name or "dirs" in metric_name:
                    # Extract state from metric name
                    for state in ["new", "changed", "unmodified"]:
                        if metric_name.endswith(state):
                            metric_type = metric_name.replace(f"_{state}", "")
                            prom_metrics.append(
                                f'restic_{metric_type}{{{labels_string},state="{state}"}} {value}'
                            )
                            break
                    else:
                        prom_metrics.append(
                            f"restic_{metric_name}{{{labels_string}}} {value}"
                        )
                elif metric_name == "total_files_processed":
                    prom_metrics.append(
                        f'restic_files{{{labels_string},state="total"}} {value}'
                    )
                elif metric_name == "total_bytes_processed":
                    prom_metrics.append(
                        f'restic_snapshot_size_bytes{{{labels_string},type="processed"}} {value}'
                    )
                else:
                    prom_metrics.append(
                        f"restic_{metric_name}{{{labels_string}}} {value}"
                    )

        logger.debug("Metrics computed:\n{}".format("\n".join(prom_metrics)))
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

        upload_metrics(destination, authentication, no_cert_verify, metrics)
        return True

    def _write_to_file(self, destination: str, metrics: List[str]) -> bool:
        """
        Write metrics to file for node_exporter text collector

        Args:
            destination: File path
            metrics: List of Prometheus-formatted metrics

        Returns:
            True if successful, False otherwise
        """
        write_metrics_file(destination, metrics, append=self.append_mode)
        return True
