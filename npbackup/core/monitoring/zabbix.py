#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.core.monitoring.zabbix"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2026 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2026030501"

from typing import Dict, Any, List
from logging import getLogger
from npbackup.core.monitoring import MonitoringBackend

logger = getLogger()

try:
    from zabbix_utils import Sender, ItemValue

    ZABBIX_AVAILABLE = True
except ImportError:
    ZABBIX_AVAILABLE = False


class ZabbixMonitor(MonitoringBackend):
    """
    Zabbix monitoring backend implementation
    Sends metrics to Zabbix server using the Zabbix sender protocol
    Uses the official zabbix-utils library (https://github.com/zabbix/python-zabbix-utils)
    """

    def __init__(self, repo_config: dict, monitoring_config: dict):
        """
        Initialize Zabbix monitoring backend

        Args:
            repo_config: Repository configuration dictionary
        """
        super().__init__(repo_config, monitoring_config)

    def is_enabled(self) -> bool:
        if not ZABBIX_AVAILABLE:
            logger.error(
                "zabbix-utils library not available. Zabbix monitoring will be disabled."
            )
            return False

        return self.get_monitoring_value("global_zabbix.enabled", False)

    def send_metrics(
        self,
        metrics: Dict[str, Any],
        labels: Dict[str, str],
        operation: str,
        dry_run: bool = False,
    ) -> bool:
        """
        Send metrics to Zabbix server

        Args:
            metrics: Dictionary of metric names and values
            labels: Dictionary of labels/tags for the metrics
            operation: Operation name (backup, restore, etc.)
            dry_run: If True, don't actually send metrics

        Returns:
            True if successful, False otherwise
        """
        if not self.is_enabled():
            logger.debug("Zabbix monitoring not enabled in configuration.")
            return False

        if not ZABBIX_AVAILABLE:
            logger.error(
                "Cannot send Zabbix metrics: zabbix-utils library not available."
            )
            return False

        # Get Zabbix configuration
        try:
            zabbix_server = self.get_monitoring_value("global_zabbix.server")
            zabbix_port = self.get_monitoring_value("global_zabbix.port", 10051)
        except (KeyError, AttributeError) as exc:
            logger.error(f"Missing Zabbix configuration: {exc}")
            return False

        if not zabbix_server:
            logger.error("Zabbix server not configured.")
            return False

        if dry_run:
            logger.info("Dry run mode. Not sending Zabbix metrics.")
            return True

        # Convert metrics to ItemValue list
        items = self._build_item_values(
            metrics,
            labels,
            operation,
            self.instance,
        )

        # Send metrics to Zabbix
        return self._send_to_zabbix(zabbix_server, zabbix_port, items)

    def _build_item_values(
        self,
        metrics: Dict[str, Any],
        labels: Dict[str, str],
        operation: str,
        instance: str,
    ) -> List:
        """
        Convert metrics dictionary to a list of zabbix-utils ItemValue objects

        Args:
            metrics: Dictionary of metrics
            labels: Dictionary of labels
            operation: Operation name
            instance: Zabbix host identifier

        Returns:
            List of ItemValue objects
        """
        items = []
        repo_name = labels.get("repo_name", "unknown")

        # Map common metrics to Zabbix item keys
        # Format: npbackup.metric_name[repo_name,operation]
        for metric_name, value in metrics.items():
            if value is None or metric_name == "operation":
                continue

            # Create Zabbix item key with proper formatting
            # Using npbackup namespace with parameters for easy templating
            if metric_name in (
                "exec_state",
                "exec_time",
                "operation_success",
                "backup_too_small",
            ):
                item_key = f"npbackup.{metric_name}[{repo_name},{operation}]"
            else:
                # Restic-specific metrics
                item_key = f"npbackup.restic.{metric_name}[{repo_name},{operation}]"

            try:
                items.append(ItemValue(self.instance, item_key, value))
            except Exception as exc:
                logger.warning(
                    f"Failed to create Zabbix ItemValue for {metric_name}: {exc}"
                )

        logger.debug(
            f"Created {len(items)} Zabbix item values for host {self.instance}"
        )
        return items

    def _send_to_zabbix(
        self, zabbix_server: str, zabbix_port: int, items: List
    ) -> bool:
        """
        Send metrics to Zabbix server using Zabbix sender protocol

        Args:
            zabbix_server: Zabbix server hostname or IP
            zabbix_port: Zabbix server port (default 10051)
            items: List of ItemValue objects

        Returns:
            True if successful, False otherwise
        """
        if not items:
            logger.warning("No Zabbix metrics to send.")
            return True

        try:
            sender = Sender(server=zabbix_server, port=zabbix_port)
            response = sender.send(items)

            if response.failed == 0:
                logger.info(
                    f"Successfully sent {response.processed} metrics to Zabbix server {zabbix_server}:{zabbix_port}"
                )
                return True
            else:
                logger.error(
                    f"Failed to send {response.failed} out of {response.total} metrics to Zabbix"
                )
                return False
        except Exception as exc:
            logger.error(f"Failed to send metrics to Zabbix: {exc}")
            logger.debug("Trace:", exc_info=True)
            return False
