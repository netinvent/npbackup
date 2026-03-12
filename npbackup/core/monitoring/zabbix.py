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
    import zabbix_utils.exceptions

    ZABBIX_AVAILABLE = True
except ImportError:
    ZABBIX_AVAILABLE = False

try:
    import ssl
except ImportError:
    HAS_PSK = False
else:
    try:
        import sslpsk3 as sslpsk

        HAS_PSK = True
    except ImportError:
        # Import sslpsk2 if sslpsk3 is not available
        try:
            import sslpsk2 as sslpsk

            HAS_PSK = True
        except ImportError:
            HAS_PSK = False


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

        try:
            zabbix_psk = self.get_monitoring_value("global_zabbix.psk")
            zabbix_psk_identity = self.get_monitoring_value(
                "global_zabbix.psk_identity"
            )
            if zabbix_psk and zabbix_psk_identity:
                logger.debug("Using PSK authentication for Zabbix sender.")
                if not HAS_PSK:
                    logger.error(
                        "PSK authentication configured but sslpsk library not available. Cannot send Zabbix metrics using PSK."
                    )
        except (KeyError, AttributeError) as exc:
            logger.debug(f"No Zabbix PSK configuration found: {exc}")

        # WIP:// happy to json here
        # Convert metrics to ItemValue list
        items = []
        """
        items = self._build_item_values(
            metrics,
            labels,
            operation,
        )
        """
        items = self.build_json_output(metrics, operation)

        # Send metrics to Zabbix
        if HAS_PSK and zabbix_psk and zabbix_psk_identity:

            def psk_wrapper(sock, *args, **kwargs):
                # Pre-Shared Key (PSK) and PSK Identity
                psk = bytes.fromhex(zabbix_psk)
                psk_identity = zabbix_psk_identity.encode()

                return sslpsk.wrap_socket(
                    sock,
                    ssl_version=ssl.PROTOCOL_TLSv1_2,
                    ciphers="ECDHE-PSK-AES128-CBC-SHA256",
                    psk=(psk, psk_identity),
                )

            return self._send_to_zabbix(zabbix_server, zabbix_port, items, psk_wrapper)
        else:
            return self._send_to_zabbix(
                zabbix_server, zabbix_port, items, psk_wrapper=None
            )

    ''' WIP remove
    def _build_item_values(
        self,
        metrics: Dict[str, Any],
        labels: Dict[str, str],
        operation: str,
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
        backup_job = labels.get("backup_job", "unknown")

        # Map common metrics to Zabbix item keys
        # Format: npbackup.metric_name[instance,operation]
        for metric_name, value in metrics.items():
            if value is None or metric_name == "operation":
                continue

            # Create Zabbix item key with proper formatting
            # Using npbackup namespace with parameters for easy templating

            # WIP:// how do we pass various labels like os=windows into zabbix ?
            label_string = ",".join(f"{key}={value}" for key, value in labels.items())

            if metric_name in (
                "exec_state",
                "exec_time",
                "operation_success",
                "backup_too_small",
            ):
                item_key = f"npbackup.{metric_name}[{label_string}]"
            else:
                # Restic-specific metrics
                item_key = f"restic.{metric_name}[{label_string}]"

            try:
                items.append(ItemValue(self.base_labels["instance"], item_key, value))
            except Exception as exc:
                logger.warning(
                    f"Failed to create Zabbix ItemValue for {metric_name}: {exc}"
                )

        logger.debug(
            f"Created {len(items)} Zabbix item values for host {self.base_labels['instance']}"
        )
        logger.debug(
            "Zabbix items: "
            + "\n".join([f"{item.key} = {item.value}" for item in items])
        )
        return items
    '''

    def _send_to_zabbix(
        self, zabbix_server: str, zabbix_port: int, items: List, psk_wrapper=None
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
            if psk_wrapper:
                sender = Sender(
                    server=zabbix_server, port=zabbix_port, socket_wrapper=psk_wrapper
                )
            else:
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
                logger.debug(f"Zabbix response: {response}")
                return False
        except zabbix_utils.exceptions.ProcessingError as exc:
            logger.error(f"Zabbix server processing error: {exc}")
            logger.debug("Trace:", exc_info=True)
            return False
        except Exception as exc:
            logger.error(f"Failed to send metrics to Zabbix: {exc}")
            logger.debug("Trace:", exc_info=True)
            return False
