#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.core.monitoring.webhooks"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2026 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2025112601"

import json
from typing import Dict, Any, Optional
from logging import getLogger
import requests
from npbackup.core.monitoring import MonitoringBackend

logger = getLogger()


class WebhookMonitor(MonitoringBackend):
    """
    Webhook monitoring backend implementation
    Sends metrics as a simple JSON dictionary containing result and metrics
    """

    def __init__(
        self, repo_config: dict, monitoring_config: dict, append_mode: bool = False
    ):
        """
        Initialize Webhook monitoring backend

        Args:
            repo_config: Repository configuration dictionary
        """
        super().__init__(repo_config, monitoring_config)
        self.last_result = None
        self.append_mode = append_mode

    def is_enabled(self) -> bool:
        return self.get_monitoring_value("global_webhooks.enabled", False)

    def send_metrics(
        self,
        metrics: Dict[str, Any],
        operation: str,
        dry_run: bool = False,
    ) -> bool:
        """
        Write metrics to JSON file

        Args:
            metrics: Dictionary of metric names and values
            labels: Dictionary of labels/tags for the metrics
            operation: Operation name (backup, restore, etc.)
            dry_run: If True, don't actually write the file

        Returns:
            True if successful, False otherwise
        """
        if not self.is_enabled():
            logger.debug("Webhook monitoring not enabled in configuration.")
            return False

        # Get JSON-specific configuration
        try:
            # Try new config structure first, fall back to old
            destination = self.get_monitoring_value("global_webhooks.destination")

            method = self.get_monitoring_value("global_webhooks.method", "POST").upper()
            if method not in ("POST", "GET"):
                logger.error(
                    f"Invalid HTTP method {method} for webhook, defaulting to POST"
                )
                method = "POST"

            # Get optional authentication
            upload_username = self.get_monitoring_value("global_webhooks.username")

            upload_password = self.get_monitoring_value("global_webhooks.password")

            # Get optional timeout (default: 30 seconds)
            upload_timeout = self.get_monitoring_value("global_webhooks.timeout", 30)

            # Get optional SSL verification setting
            no_cert_verify = self.get_monitoring_value(
                "global_webhooks.no_cert_verify", False
            )

            # Get optional pretty print setting (default: True for readability)
            pretty_print = self.get_monitoring_value(
                "global_webhooks.pretty_json", False
            )

        except (KeyError, AttributeError) as exc:
            logger.error(f"Missing Webhooks configuration: {exc}")
            return False

        if not destination:
            logger.error("Webhook destination not configured.")
            return False

        if dry_run:
            logger.info("Dry run mode. Not sending webhook.")
            return True

        # Build the output structure
        output = self.build_json_output(metrics, operation)

        # Store the result for potential retrieval
        self.last_result = output

        success = True

        # Upload to HTTP endpoint if configured
        if destination and (
            destination.startswith("http://") or destination.startswith("https://")
        ):
            auth = None
            if upload_username and upload_password:
                auth = (upload_username, upload_password)

            upload_success = self._upload_json(
                destination, method, output, auth, upload_timeout, no_cert_verify
            )
            if not upload_success:
                success = False

        # Write to file if destination is specified
        elif destination:
            file_success = self._write_json_file(
                destination, output, pretty_print, self.append_mode
            )
            if not file_success:
                success = False
        else:
            logger.warning(f"Destination not configured for webhooks")

        return success

    def _write_json_file(
        self,
        destination: str,
        data: Dict[str, Any],
        pretty_print: bool = True,
        append_mode: bool = False,
    ) -> bool:
        """
        Write JSON data to file

        Args:
            destination: File path
            data: Data to write
            pretty_print: Whether to format JSON with indentation
            append_mode: Whether to append to existing file (creates array)

        Returns:
            True if successful, False otherwise
        """
        try:
            if append_mode:
                # In append mode, we maintain a JSON array
                existing_data = []
                try:
                    with open(destination, "r", encoding="utf-8") as f:
                        content = f.read().strip()
                        if content:
                            existing_data = json.loads(content)
                            # Ensure it's a list
                            if not isinstance(existing_data, list):
                                existing_data = [existing_data]
                except FileNotFoundError:
                    # File doesn't exist yet, start with empty list
                    pass
                except json.JSONDecodeError:
                    logger.warning(
                        f"Could not parse existing JSON file {destination}, starting fresh"
                    )
                    existing_data = []

                # Append new data
                existing_data.append(data)
                write_data = existing_data
            else:
                # Overwrite mode - just write the current data
                write_data = data

            # Write the file
            with open(destination, "w", encoding="utf-8") as f:
                if pretty_print:
                    json.dump(write_data, f, indent=2, ensure_ascii=False)
                else:
                    json.dump(write_data, f, ensure_ascii=False)
                f.write("\n")  # Add final newline

            logger.info(f"JSON metrics written to {destination}")
            return True

        except OSError as exc:
            logger.error(f"Failed to write JSON metrics file {destination}: {exc}")
            logger.debug("Trace:", exc_info=True)
            return False
        except Exception as exc:
            logger.error(f"Unexpected error writing JSON metrics: {exc}")
            logger.debug("Trace:", exc_info=True)
            return False

    def _upload_json(
        self,
        destination: str,
        method: str,
        data: Dict[str, Any],
        auth: Optional[tuple] = None,
        timeout: int = 30,
        no_cert_verify: bool = False,
    ) -> bool:
        """
        Upload JSON data to HTTP endpoint

        Args:
            destination: Upload URL
            data: Data to upload
            auth: Optional tuple of (username, password)
            timeout: Request timeout in seconds
            no_cert_verify: Whether to skip SSL certificate verification

        Returns:
            True if successful, False otherwise
        """
        try:
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "npbackup-json-monitor",
            }

            if method == "GET":
                response = requests.get(
                    destination,
                    params=data,
                    headers=headers,
                    auth=auth,
                    timeout=timeout,
                    verify=not no_cert_verify,
                )
            else:
                response = requests.post(
                    destination,
                    json=data,
                    headers=headers,
                    auth=auth,
                    timeout=timeout,
                    verify=not no_cert_verify,
                )

            if response.status_code in (200, 201, 202, 204):
                logger.info(f"Successfully uploaded JSON metrics to {destination}")
                return True
            else:
                logger.warning(
                    f"JSON upload returned status {response.status_code}: {response.text}"
                )
                return False

        except requests.RequestException as exc:
            logger.error(f"Failed to upload JSON metrics to {destination}: {exc}")
            logger.debug("Trace:", exc_info=True)
            return False
        except Exception as exc:
            logger.error(
                f"Unexpected error uploading JSON metrics to {destination}: {exc}"
            )
            logger.debug("Trace:", exc_info=True)
            return False

    def get_last_result(self) -> Optional[Dict[str, Any]]:
        """
        Get the last result that was sent/written

        Returns:
            Dictionary with result and metrics, or None if no result yet
        """
        return self.last_result
