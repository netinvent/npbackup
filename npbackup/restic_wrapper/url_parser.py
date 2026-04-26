#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.restic_wrapper.url_parser"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2026 NetInvent"
__license__ = "GPL-3.0-only"
__description__ = "Restic url parser and rebuilder"


from typing import Tuple, Optional
import copy
import re
from urllib.parse import urlparse, unquote, uses_netloc as _urllib_uses_netloc

# urlparse only splits out netloc (and thus hostname/port) for schemes it
# knows about.  Register http+unix and https+unix so that port detection
# works correctly for those schemes as well.
for _scheme in ("http+unix", "https+unix"):
    if _scheme not in _urllib_uses_netloc:
        _urllib_uses_netloc.append(_scheme)
import ipaddress


def parse_restic_repo(repo_uri: str) -> dict:
    """
    Parse a restic repository URI into structured components
    Trying to mimic restic repo parsing here
    """

    def _parse_restic_repo(repo_uri: str) -> dict:
        """
        Parse a restic repository string with behavior close to restic CLI.

        Returns a dict with:
        - backend
        - backend-specific fields
        """

        def strip_ipv6_brackets(host: Optional[str]) -> Optional[str]:
            if host and host.startswith("[") and host.endswith("]"):
                return host[1:-1]
            return host

        def _parse_rest(rest: str) -> dict:
            parsed = urlparse(rest)
            if parsed.scheme not in ("http", "http+unix", "https", "https+unix"):
                raise ValueError(
                    f"rest backend requires http or https, http+unix, or https+unix scheme, got: {rest}"
                )

            return {
                "backend_type": "rest",
                "scheme": parsed.scheme,
                "username": unquote(parsed.username) if parsed.username else None,
                "password": unquote(parsed.password) if parsed.password else None,
                "host": parsed.hostname,
                "port": parsed.port,
                "path": parsed.path or None,
            }

        def _parse_sftp(rest: str) -> dict:
            """
            Parse SFTP URI with optional port.
            Supports:
            user@host:path
            user@host:port:path
            user@[ipv6]:path
            user@[ipv6]:port:path
            """

            # Step 0: restic can do sftp://user@host:port//path or sftp:user@host:/path but only the url syntax allows custom ports
            if rest.startswith("//"):
                rest = rest[2:]

            # Step 1: optional user@
            if "@" in rest:
                user, rest2 = rest.split("@", 1)
            else:
                user, rest2 = None, rest

            # Step 2: detect host (IPv6 or hostname)
            if rest2.startswith("["):
                end = rest2.find("]")
                if end == -1:
                    raise ValueError("Invalid IPv6 host")
                host = rest2[1:end]
                remainder = rest2[end + 1 :]
                if not remainder.startswith(":"):
                    raise ValueError("Missing ':' after IPv6 host")
                remainder = remainder[1:]  # strip colon
            else:
                if ":" not in rest2:
                    raise ValueError("Missing ':' separator for path")
                host, remainder = rest2.split(":", 1)

            # Step 3: detect optional port
            port = None
            path = remainder

            # Split on first '/' in remainder to separate port and path
            if "/" in remainder:
                first, rest_path = remainder.split("/", 1)
                if first.isdigit():
                    port = int(first)
                    path = "/" + rest_path  # restore leading slash
                else:
                    path = remainder  # entire remainder is path
            else:
                # no slash, could still be port (rare case)
                if remainder.isdigit():
                    port = int(remainder)
                    path = None
                else:
                    path = remainder

            if not path:
                raise ValueError("Missing SFTP path")

            return {
                "backend_type": "sftp",
                "username": user,
                "host": host,
                "port": port,
                "path": path,
            }

        def _parse_s3(rest: str) -> dict:
            # restic allows:
            # s3:bucket/path
            # s3:host/bucket/path
            # s3:https://host/bucket/path

            if rest.startswith("http://") or rest.startswith("https://"):
                parsed = urlparse(rest)
                parts = parsed.path.lstrip("/").split("/", 1)

                bucket = parts[0] if parts else None
                path = parts[1] if len(parts) > 1 else None

                return {
                    "backend_type": "s3",
                    "endpoint": parsed.netloc,
                    "bucket": bucket,
                    "path": path,
                    "secure": parsed.scheme == "https",
                }

            parts = rest.split("/", 2)

            if len(parts) == 1:
                return {
                    "backend_type": "s3",
                    "endpoint": None,
                    "bucket": parts[0],
                    "path": None,
                }

            # heuristic: first part contains dot or colon → endpoint
            if "." in parts[0] or ":" in parts[0]:
                raw_endpoint = parts[0]
                # Split host:port when an explicit port is present
                if ":" in raw_endpoint:
                    ep_host, ep_port_str = raw_endpoint.rsplit(":", 1)
                    if ep_port_str.isdigit():
                        endpoint = ep_host
                        port = int(ep_port_str)
                    else:
                        endpoint = raw_endpoint
                        port = None
                else:
                    endpoint = raw_endpoint
                    port = None
                bucket = parts[1] if len(parts) > 1 else None
                path = parts[2] if len(parts) > 2 else None
                return {
                    "backend_type": "s3",
                    "endpoint": endpoint,
                    "port": port,
                    "bucket": bucket,
                    "path": path,
                }
            else:
                endpoint = None
                bucket = parts[0]
                path = parts[1] if len(parts) > 1 else None

            return {
                "backend_type": "s3",
                "endpoint": endpoint,
                "bucket": bucket,
                "path": path,
            }

        def _parse_b2(rest: str) -> dict:
            bucket, _, path = rest.partition("/")
            return {
                "backend_type": "b2",
                "bucket": bucket,
                "path": path or None,
            }

        def _parse_azure(rest: str) -> dict:
            container, _, path = rest.partition("/")
            return {
                "backend_type": "azure",
                "container": container,
                "path": path or None,
            }

        def _parse_gs(rest: str) -> dict:
            bucket, _, path = rest.partition("/")
            return {
                "backend_type": "gs",
                "bucket": bucket,
                "path": path or None,
            }

        def _parse_swift(rest: str) -> dict:
            container, _, path = rest.partition("/")
            return {
                "backend_type": "swift",
                "container": container,
                "path": path or None,
            }

        def _parse_rclone(rest: str) -> dict:
            # IMPORTANT: split only on first colon
            remote, sep, path = rest.partition(":")
            if not sep:
                raise ValueError("invalid rclone format")

            return {
                "backend_type": "rclone",
                "remote": remote,
                "path": path or None,
            }

        def _parse_local(path: str) -> dict:
            return {
                "backend_type": "local",
                "path": path,
            }

        # Windows drive letter → local
        if re.match(r"^[a-zA-Z]:\\", repo_uri):
            return _parse_local(repo_uri)

        if ":" not in repo_uri:
            return _parse_local(repo_uri)

        backend, actual_uri = repo_uri.split(":", 1)

        handlers = {
            "rest": _parse_rest,
            "sftp": _parse_sftp,
            "s3": _parse_s3,
            "b2": _parse_b2,
            "azure": _parse_azure,
            "gs": _parse_gs,
            "swift": _parse_swift,
            "rclone": _parse_rclone,
        }

        if backend in handlers:
            return handlers[backend](actual_uri)

        # Unknown backend → restic treats as local path
        return _parse_local(repo_uri)

    def _validate_restic_repo(parsed: dict) -> None:
        """
        Raises ValueError if validation fails.
        Returns None if valid.
        """

        backend_type = parsed.get("backend_type")

        def validate_port(port) -> None:
            if port is None:
                return
            if not (1 <= port <= 65535):
                raise ValueError(f"Invalid port: {port}")

        def validate_hostname(host) -> None:
            if not host:
                raise ValueError("Missing host")

            # Try IP (v4/v6)
            try:
                ipaddress.ip_address(host)
                return
            except ValueError:
                pass

            if len(host) > 253:  # DNS max length AFAIK
                raise ValueError("Hostname too long")

            labels = host.split(".")
            hostname_re = re.compile(r"^[a-zA-Z0-9-]{1,63}$")

            for label in labels:
                if not hostname_re.match(label):
                    raise ValueError(f"Invalid hostname label: {label}")
                if label.startswith("-") or label.endswith("-"):
                    raise ValueError(f"Invalid hostname label: {label}")

        def validate_path(path) -> None:
            if path is None:
                raise ValueError("Missing path")
            if not path.startswith("/"):
                raise ValueError(f"Path must start with '/': {path}")
            if "//" in path:
                raise ValueError(f"Invalid path (double slash): {path}")

        # AWS-style bucket rules (simplified but strict enough)
        bucket_re = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")

        def validate_bucket(name) -> None:
            if not name:
                raise ValueError("Missing bucket/container name")

            if not bucket_re.match(name):
                raise ValueError(f"Invalid bucket name: {name}")

            if ".." in name or ".-" in name or "-." in name:
                raise ValueError(f"Invalid bucket name: {name}")

        if backend_type == "rest":
            if parsed.get("scheme") not in ("http", "https", "http+unix", "https+unix"):
                raise ValueError(
                    f"REST backend validator requires http/https, http+unix, or https+unix scheme, got: {parsed}"
                )

            # http+unix / https+unix URIs with a triple-slash (e.g.
            # http+unix:///tmp/sock:/repo) have an empty netloc, so host is
            # legitimately None. Only validate the hostname when it is present.
            if parsed.get("host") is not None:
                validate_hostname(parsed.get("host"))
            elif parsed.get("scheme") not in ("http+unix", "https+unix"):
                raise ValueError("Missing host")
            validate_port(parsed.get("port"))
            validate_path(parsed.get("path"))

        elif backend_type == "sftp":
            validate_hostname(parsed.get("host"))

            path = parsed.get("path")
            if not path:
                raise ValueError("Missing path")

        elif backend_type == "s3":
            validate_bucket(parsed.get("bucket"))

            endpoint = parsed.get("endpoint")
            if endpoint:
                # port is now stored as a separate field
                validate_hostname(endpoint)
                validate_port(parsed.get("port"))

        elif backend_type in ("b2", "gs"):
            validate_bucket(parsed.get("bucket"))

        elif backend_type in ("azure", "swift"):
            validate_bucket(parsed.get("container"))

        elif backend_type == "rclone":
            if not parsed.get("remote"):
                raise ValueError("Missing rclone remote")

        elif backend_type == "local":
            path = parsed.get("path")
            if not path:
                raise ValueError("Missing local path")
            if "\0" in path:
                raise ValueError("Invalid local path")

        else:
            raise ValueError(f"Unknown backend: {backend_type}")

    if isinstance(repo_uri, str):
        repo_uri_dict = _parse_restic_repo(repo_uri)
        _validate_restic_repo(repo_uri_dict)
        # After validation, we want to me sure we can reconstruct the URI as identical string
        reconstructed_uri = build_restic_uri(repo_uri_dict)
        if reconstructed_uri != repo_uri:
            if repo_uri.startswith("sftp:") and reconstructed_uri.startswith("sftp://"):
                # Special case: restic accepts both sftp:user@host:/path and sftp://user@host//path
                # If ports are present we'll normalize it
                if reconstructed_uri[7:] == repo_uri[5:]:
                    return repo_uri_dict
            raise ValueError(
                f"Parsed URI does not reconstruct to original. Got: {reconstructed_uri}, expected: {repo_uri}"
            )
    else:
        return {}
    return repo_uri_dict


def build_restic_uri(_repo_uri_dict: dict, anonymized: bool = False) -> str:
    repo_uri_dict = copy.deepcopy(_repo_uri_dict)
    backend_type = repo_uri_dict.get("backend_type")

    host = repo_uri_dict.get("host")
    scheme = repo_uri_dict.get("scheme")
    if not scheme:
        try:
            scheme = urlparse(host).scheme
        except Exception:
            scheme = None
    if host:
        try:
            # Only IPv6 addresses need brackets in URIs; IPv4 must not be bracketed.
            if isinstance(ipaddress.ip_address(host), ipaddress.IPv6Address):
                repo_uri_dict["host"] = f"[{host}]"
        except (ValueError, TypeError):
            pass
    if backend_type == "rest":
        if scheme not in ("http", "http+unix", "https", "https+unix"):
            raise ValueError(
                f"rest backend builder requires http or https, http+unix, or https+unix scheme, got: {scheme}"
            )

        auth = ""
        if repo_uri_dict.get("username"):
            auth += repo_uri_dict["username"]
            if repo_uri_dict.get("password"):
                # NPF-SEC-00014
                if anonymized:
                    auth += ":___[o_0]___"
                else:
                    auth += f":{repo_uri_dict['password']}"
            auth += "@"
        host = repo_uri_dict.get("host") or ""  # None for http+unix with empty netloc
        port = f":{repo_uri_dict['port']}" if repo_uri_dict.get("port") else ""
        path = repo_uri_dict.get("path") or ""
        if path and not path.startswith("/"):
            path = (
                "/" + path
            )  # ensure path starts with slash for correct round-tripping
        return f"{backend_type}:{scheme}://{auth}{host}{port}{path}"

    elif backend_type == "sftp":
        user = f"{repo_uri_dict['username']}@" if repo_uri_dict.get("username") else ""
        host = repo_uri_dict[
            "host"
        ]  # already bracketed by top-level IPv6 check if needed
        # The colon is always required as host/path separator in SCP-style SFTP URIs.
        # When a port is present it contributes the colon (e.g. ":22"), otherwise we
        # must emit a bare ":" so that host:/path round-trips correctly.
        port = f":{repo_uri_dict['port']}" if repo_uri_dict.get("port") else ":"
        path = repo_uri_dict["path"]
        if path and not path.startswith("/"):
            path = (
                "/" + path
            )  # ensure path starts with slash for correct round-tripping
        # restic can use either sftp:user@host:/path or sftp://user@host:port//path syntax, only the latter supports custom ports
        if port != ":":
            return f"{backend_type}://{user}{host}{port}{path}"
        else:
            return f"{backend_type}:{user}{host}{port}{path}"

    elif backend_type == "s3":
        endpoint = repo_uri_dict.get("endpoint")
        bucket = repo_uri_dict["bucket"]
        path = repo_uri_dict.get("path")
        if endpoint:
            secure = repo_uri_dict.get("secure")
            if secure is not None:
                # URL-style endpoint (s3:https://...): port is already in netloc
                scheme = "https" if secure else "http"
                endpoint = f"{scheme}://{endpoint}"
            else:
                # Plain endpoint: reattach port when present
                port = repo_uri_dict.get("port")
                if port is not None:
                    endpoint = f"{endpoint}:{port}"
            return (
                f"{backend_type}:{endpoint}/{bucket}/{path}"
                if path
                else f"{backend_type}:{endpoint}/{bucket}"
            )
        else:
            return (
                f"{backend_type}:{bucket}/{path}"
                if path
                else f"{backend_type}:{bucket}"
            )

    elif backend_type in ("b2", "gs"):
        bucket = repo_uri_dict["bucket"]
        path = repo_uri_dict.get("path")
        return f"{backend_type}:{bucket}/{path}" if path else f"{backend_type}:{bucket}"

    elif backend_type in ("azure", "swift"):
        container = repo_uri_dict["container"]
        path = repo_uri_dict.get("path")
        return (
            f"{backend_type}:{container}/{path}"
            if path
            else f"{backend_type}:{container}"
        )

    elif backend_type == "rclone":
        remote = repo_uri_dict["remote"]
        path = repo_uri_dict.get("path")
        return (
            f"{backend_type}:{remote}:{path}" if path else f"{backend_type}:{remote}:"
        )

    elif backend_type == "local":
        return repo_uri_dict["path"]

    else:
        raise ValueError(f"Unknown backend: {backend_type}")


def get_anon_repo_uri(repo_uri: str) -> Tuple[str, str]:
    """
    Wrapper for earlier get_anon_repo_uri implementation
    Get a restic repository URI with credentials removed, for display purposes
    """
    try:
        repo_uri_dict = parse_restic_repo(repo_uri)
        return repo_uri_dict["backend_type"], build_restic_uri(
            repo_uri_dict, anonymized=True
        )
    except (ValueError, KeyError):
        return "Unknown", "CannotParseUrl"
