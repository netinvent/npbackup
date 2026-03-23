#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.core.monitoring.zabbix"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2026 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2026032301"

import sys
import json
from typing import Dict, Any, List
from time import sleep
from logging import getLogger
from npbackup.core.monitoring import MonitoringBackend

logger = getLogger()

try:
    from zabbix_utils import Sender, ItemValue
    import zabbix_utils.exceptions

    ZABBIX_AVAILABLE = True
except ImportError:
    ZABBIX_AVAILABLE = False

ZABBIX_DISCOVERY_SENT = False

try:
    import ssl
except ImportError:
    HAVE_SSL = False
else:
    HAVE_SSL = True
    if sys.version_info[0] >= 3 and sys.version_info[1] <= 12:
        NEED_PSK_MODULE = True
        try:
            import sslpsk3 as sslpsk

            HAVE_PSK_MODULE = True
        except ImportError:
            # Import sslpsk2 if sslpsk3 is not available
            try:
                import sslpsk2 as sslpsk

                HAVE_PSK_MODULE = True
            except ImportError:
                HAVE_PSK_MODULE = False
                sslpsk = None
    else:
        NEED_PSK_MODULE = False
        HAVE_PSK_MODULE = False
        sslpsk = None


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
        self.repo_name = repo_config.g("name")
        self.action = self.common_labels.get("action", "unknown")

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
        global ZABBIX_DISCOVERY_SENT

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

        # WIP: to implement: raw JSON protocol
        try:
            zabbix_send_method = self.get_monitoring_value("global_zabbix.method")
        except (KeyError, AttributeError) as exc:
            logger.debug(
                f"No Zabbix send method configured, defaulting to ZabbixProtocol: {exc}"
            )
            zabbix_send_method = "ZabbixProtocol"

        no_cert_verify = self.get_monitoring_value(
            "global_zabbix.no_cert_verify", False
        )
        zabbix_auth = self.get_monitoring_value(
            "global_zabbix.authentication", "none"
        ).lower()
        zabbix_psk = None
        zabbix_psk_identity = None
        try:
            zabbix_psk = self.get_monitoring_value("global_zabbix.psk")
            zabbix_psk_identity = self.get_monitoring_value(
                "global_zabbix.psk_identity"
            )
        except (KeyError, AttributeError) as exc:
            logger.debug(f"No Zabbix PSK configuration found: {exc}")
            zabbix_psk = None
            zabbix_psk_identity = None

        try:
            tls_cert = self.get_monitoring_value("global_zabbix.tls_cert")
            tls_key = self.get_monitoring_value("global_zabbix.tls_key")
            tls_cacert = self.get_monitoring_value("global_zabbix.tls_cacert")
        except (KeyError, AttributeError) as exc:
            logger.debug(f"No Zabbix TLS certificate configuration found: {exc}")
            tls_cert = None
            tls_key = None
            tls_cacert = None

        if zabbix_auth in ["tls", "psk"]:
            if not HAVE_SSL:
                logger.error(
                    f"Zabbix authentication method '{zabbix_auth}' requires SSL support, but ssl module is not available."
                )
                return False
            if zabbix_auth == "psk" and NEED_PSK_MODULE and not HAVE_PSK_MODULE:
                logger.error(
                    "Zabbix PSK authentication requires sslpsk module, but it is not available."
                )
                return False
            if zabbix_auth == "psk" and (not zabbix_psk or not zabbix_psk_identity):
                logger.error(
                    "Zabbix PSK authentication requires both PSK key and identity to be configured."
                )
                return False
            if zabbix_auth == "tls" and (not tls_cert or not tls_key or not tls_cacert):
                logger.error(
                    "Zabbix TLS authentication requires certificate, key and CA certificate to be configured."
                )
                return False

        if zabbix_auth == "psk":
            if NEED_PSK_MODULE and HAVE_PSK_MODULE:

                def socket_wrapper(sock, *args, **kwargs):
                    psk = bytes.fromhex(zabbix_psk)
                    psk_identity = zabbix_psk_identity.encode()

                    return sslpsk.wrap_socket(
                        sock,
                        ssl_version=ssl.PROTOCOL_TLSv1_2,
                        ciphers="ECDHE-PSK-AES128-CBC-SHA256",
                        psk=(psk, psk_identity),
                    )

            else:

                def socket_wrapper(sock, *args, **kwargs):
                    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                    context.check_hostname = not no_cert_verify
                    context.verify_mode = ssl.CERT_NONE
                    context.maximum_version = ssl.TLSVersion.TLSv1_2
                    context.set_ciphers("PSK")
                    context.set_psk_client_callback(
                        lambda hint: (
                            zabbix_psk_identity.encode(),
                            bytes.fromhex(zabbix_psk),
                        )
                    )
                    return context.wrap_socket(sock)

        elif zabbix_auth == "tls":

            def socket_wrapper(sock, *args, **kwargs):
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                context.load_cert_chain(tls_cert, keyfile=tls_key)
                context.load_verify_locations(cafile=tls_cacert)
                context.check_hostname = not no_cert_verify
                context.verify_mode = ssl.VerifyMode.CERT_REQUIRED
                return context.wrap_socket(sock, server_hostname=zabbix_server)

        else:

            def socket_wrapper(sock, *args, **kwargs):
                return sock

        if dry_run:
            logger.info("Dry run mode. Not sending Zabbix metrics.")
            return True

        # Send LLD discovery data so Zabbix creates items from prototypes
        self._send_discovery(zabbix_server, zabbix_port, socket_wrapper)
        # Now let's sleep arbitrary 10 seconds to give zabbix server time to process the discovery
        # WIP: This could perhaps be improved by checking the Zabbix server for the existence of
        # the discovered items before sending metrics (requires API client)
        # As for now, let's just be full stupid cand keep a global variable around

        # Plain stupid global variable here...
        # We would need to keep track of discovery sent per target somehow
        if not ZABBIX_DISCOVERY_SENT:
            ZABBIX_DISCOVERY_SENT = True
            logger.info(
                "Sent Zabbix discovery data. Sleeping 10 seconds to allow Zabbix server to process data before sending metrics"
            )
            sleep(10)

        # Convert metrics to ItemValue list and send
        items = self._build_item_values(metrics, operation)
        return self._send_to_zabbix(zabbix_server, zabbix_port, items, socket_wrapper)

    def _build_item_values(
        self,
        metrics: Dict[str, Any],
        operation: str,
    ) -> List:
        """
        Convert metrics dictionary to a list of zabbix-utils ItemValue objects.

        Uses positional key parameters [repo_name,action] to match Zabbix LLD
        item prototypes. The "instance" label is used as the Zabbix host.

        Args:
            metrics: Dictionary of metrics
            operation: Operation name

        Returns:
            List of ItemValue objects
        """
        items = []
        instance = self.common_labels.get("instance", "default_instance")

        for metric_name, value in metrics.items():
            if value is None:
                continue

            if metric_name.startswith("npbackup_"):
                # Map upgrade state to npbackup.exec_state with action=upgrade
                if metric_name == "npbackup_upgrade_state":
                    item_key = f"npbackup.exec_state[{self.repo_name},upgrade]"
                else:
                    short_name = metric_name[len("npbackup_") :]
                    item_key = f"npbackup.{short_name}[{self.repo_name},{operation}]"
                try:
                    items.append(
                        ItemValue(
                            instance, item_key, value, clock=self.metrics_timestamp
                        )
                    )
                except Exception as exc:
                    logger.warning(
                        f"Failed to create Zabbix ItemValue for {metric_name}: {exc}"
                    )

            elif metric_name.startswith("restic_"):
                short_name = metric_name[len("restic_") :]
                if isinstance(value, dict):
                    # Flatten dict metrics, e.g. restic_files: {"new": 5, "changed": 3}
                    # becomes restic.files[repo,action,new] = 5
                    for sub_metric, sub_value in value.items():
                        if sub_value is None:
                            continue
                        item_key = f"restic.{short_name}[{self.repo_name},{operation},{sub_metric}]"
                        try:
                            items.append(
                                ItemValue(
                                    instance,
                                    item_key,
                                    sub_value,
                                    clock=self.metrics_timestamp,
                                )
                            )
                        except Exception as exc:
                            logger.warning(
                                f"Failed to create Zabbix ItemValue for {metric_name}.{sub_metric}: {exc}"
                            )
                else:
                    item_key = f"restic.{short_name}[{self.repo_name},{self.action}]"
                    try:
                        items.append(
                            ItemValue(
                                instance, item_key, value, clock=self.metrics_timestamp
                            )
                        )
                    except Exception as exc:
                        logger.warning(
                            f"Failed to create Zabbix ItemValue for {metric_name}: {exc}"
                        )
            else:
                logger.warning(f"Unknown metric namespace for {metric_name}, skipping.")

        logger.debug(f"Created {len(items)} Zabbix item values for host {instance}")
        if items:
            logger.debug(
                "Zabbix items:\n"
                + "\n".join(f"  {item.key} = {item.value}" for item in items)
            )
        return items

    def _send_discovery(
        self,
        zabbix_server: str,
        zabbix_port: int,
        socket_wrapper=None,
    ) -> bool:
        """
        Send Low-Level Discovery data to Zabbix so trapper item prototypes
        are instantiated for this repo/action combination.

        All common_labels are sent as LLD macros so they can be used as
        tags on discovered items, mirroring how Prometheus exposes labels.
        """
        instance = self.common_labels.get("instance", "default_instance")

        # Build LLD entity with all common labels as macros
        # ("instance" is the Zabbix host, not an LLD macro)
        lld_entity = {}
        for label, value in self.common_labels.items():
            if label == "instance":
                continue
            macro_name = "{#" + label.upper() + "}"
            lld_entity[macro_name] = str(value) if value is not None else ""

        lld_data = json.dumps([lld_entity])

        items = [
            ItemValue(
                instance, "npbackup.discovery", lld_data, clock=self.metrics_timestamp
            )
        ]

        logger.debug(
            f"Sending Zabbix LLD data for host {instance}: repo={self.repo_name}, action={self.action}"
        )
        return self._send_to_zabbix(zabbix_server, zabbix_port, items, socket_wrapper)

    def _send_to_zabbix(
        self, zabbix_server: str, zabbix_port: int, items: List, socket_wrapper=None
    ) -> bool:
        """
        Send metrics to Zabbix server using Zabbix sender protocol

        Args:
            zabbix_server: Zabbix server hostname or IP
            zabbix_port: Zabbix server port (default 10051)
            items: List of ItemValue objects
            socket_wrapper: optional function to use tls / tls-psk or psk

        Returns:
            True if successful, False otherwise
        """
        if not items:
            logger.warning("No Zabbix metrics to send.")
            return True

        try:
            if socket_wrapper:
                sender = Sender(
                    server=zabbix_server,
                    port=zabbix_port,
                    socket_wrapper=socket_wrapper,
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
