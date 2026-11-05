#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.export4x"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2026 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2026110401"


"""
NPF-SEC-00018: Hand this machine's configuration over to NPBackup 4.x, never in clear

4.x cannot read this configuration: its secrets are encrypted with the key compiled into
this build. So this program decrypts it, and seals it for the one-time public key the 4.x
installer made for this migration (--export-for-4x <key>), with HPKE (RFC 9180):
DHKEM(X25519, HKDF-SHA256), HKDF-SHA256, AES-256-GCM, base mode. Only the sealed block is
written, on stdout; there is no clear mode. Its header lines are the associated data: in
clear, and bound to the content.

HPKE's steps are taken here, from pycryptodomex's X25519 and AES-GCM and Python's own HMAC:
pycryptodomex's HPKE module cannot be imported before Python 3.9 (it writes its signatures
tuple[bytes, bytes]), and the legacy builds run Python 3.7.

Only an administrator may export, and a manager password set on a repository or group must
be given in NPBACKUP_MANAGER_PASSWORD, as with --show-config.
The configuration file is read through a private copy, so the loader never rewrites it
"""

import os
import json
import hmac
import base64
import hashlib
import platform
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from logging import getLogger
from pathlib import Path
from time import sleep
import npbackup.configuration
from npbackup.__version__ import version_dict

logger = getLogger()

BEGIN = "-----BEGIN NPBACKUP 3.X EXPORT-----"
END = "-----END NPBACKUP 3.X EXPORT-----"
# The block's version: 4.x opens only one it knows
VERSION = "1"
# HPKE's info, which every key of a block is derived with
INFO = b"npbackup 3.x export to 4.x, v1"
# RFC 9180's identifiers of DHKEM(X25519, HKDF-SHA256), HKDF-SHA256 and AES-256-GCM
KEM_ID, KDF_ID, AEAD_ID = 0x0020, 0x0001, 0x0002
KEM_SUITE = b"KEM" + KEM_ID.to_bytes(2, "big")
HPKE_SUITE = b"HPKE" + b"".join(i.to_bytes(2, "big") for i in (KEM_ID, KDF_ID, AEAD_ID))


class ExportRefused(Exception):
    """An export not made, why, and the exit code that says so"""

    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


def is_admin() -> bool:
    """Root, or an elevated administrator on Windows"""
    if os.name == "nt":
        try:
            import ctypes

            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:  # pylint: disable=W0703 (broad-except)
            return False
    return os.geteuid() == 0


def primitives():
    """
    pycryptodomex's AES, X25519 keys and key agreement, from pycryptodomex 3.23 on, which
    Python 3.7 imports: imported for an export only, and a build without them says so
    """
    try:
        from Cryptodome.Cipher import AES
        from Cryptodome.PublicKey import ECC
        from Cryptodome.Protocol.DH import import_x25519_public_key, key_agreement
    except Exception as exc:  # pylint: disable=W0703 (broad-except): not only ImportError
        raise ExportRefused(
            "This build cannot seal for NPBackup 4.x, which needs pycryptodomex 3.23 or later "
            f"(this is Python {platform.python_version()}): {exc}",
            12,
        ) from exc
    return AES, ECC, import_x25519_public_key, key_agreement


def _labeled_extract(suite: bytes, salt: bytes, label: bytes, ikm: bytes) -> bytes:
    """RFC 9180's LabeledExtract: HKDF-Extract, with SHA-256"""
    return hmac.new(salt, b"HPKE-v1" + suite + label + ikm, hashlib.sha256).digest()


def _labeled_expand(suite: bytes, prk: bytes, label: bytes, info: bytes, length: int) -> bytes:
    """RFC 9180's LabeledExpand: HKDF-Expand, with SHA-256"""
    labeled = length.to_bytes(2, "big") + b"HPKE-v1" + suite + label + info
    output, block, counter = b"", b"", 1
    while len(output) < length:
        block = hmac.new(prk, block + labeled + bytes([counter]), hashlib.sha256).digest()
        output += block
        counter += 1
    return output[:length]


def hpke_seal(recipient: bytes, info: bytes, associated: bytes, plaintext: bytes) -> bytes:
    """
    HPKE's base mode, one message (RFC 9180, 4.1, 5.1, 5.2), for the X25519 public key
    recipient (its 32 bytes): the encapsulated key, then the ciphertext and its tag
    """
    AES, ECC, import_x25519_public_key, key_agreement = primitives()
    ephemeral = ECC.generate(curve="Curve25519")
    dh = key_agreement(
        static_priv=ephemeral,
        static_pub=import_x25519_public_key(recipient),
        kdf=lambda shared: shared,
    )
    if not any(dh):
        raise ExportRefused("The 4.x installer's key gives no shared secret: it is no key", 2)
    enc = ephemeral.public_key().export_key(format="raw")
    eae_prk = _labeled_extract(KEM_SUITE, b"", b"eae_prk", dh)
    shared_secret = _labeled_expand(KEM_SUITE, eae_prk, b"shared_secret", enc + recipient, 32)
    context = (
        b"\x00"
        + _labeled_extract(HPKE_SUITE, b"", b"psk_id_hash", b"")
        + _labeled_extract(HPKE_SUITE, b"", b"info_hash", info)
    )
    secret = _labeled_extract(HPKE_SUITE, shared_secret, b"secret", b"")
    key = _labeled_expand(HPKE_SUITE, secret, b"key", context, 32)
    nonce = _labeled_expand(HPKE_SUITE, secret, b"base_nonce", context, 12)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    cipher.update(associated)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext)
    return enc + ciphertext + tag


def recipient_key(public_key: str):
    """The 4.x installer's public key, given as the base64 of its 32 bytes, and those bytes"""
    _, _, import_x25519_public_key, _ = primitives()
    try:
        raw = base64.b64decode(public_key.strip(), validate=True)
        return import_x25519_public_key(raw), raw
    except (ValueError, TypeError) as exc:
        raise ExportRefused(
            f"{public_key} is not the 4.x installer's public key: {exc}", 2
        ) from exc


def fingerprint(raw: bytes) -> str:
    """What the log says of a key: enough to tell keys apart, nothing to use"""
    return hashlib.sha256(raw).hexdigest()[:16]


def seal(public_key: str, headers: list, payload: bytes) -> str:
    """
    The sealed block of payload for public_key: headers in clear, then Recipient, all of
    them bound to the content
    """
    _, raw = recipient_key(public_key)
    headers = list(headers) + [("Recipient", base64.b64encode(raw).decode("ascii"))]
    associated = "".join(f"{name}: {value}\n" for name, value in headers).encode("utf-8")
    body = base64.b64encode(hpke_seal(raw, INFO, associated, payload)).decode("ascii")
    lines = [BEGIN] + [f"{name}: {value}" for name, value in headers] + [""]
    lines += [body[i : i + 64] for i in range(0, len(body), 64)]
    lines.append(END)
    return "\n".join(lines) + "\n"


def manager_passwords(full_config) -> list:
    """The repositories and groups with a manager password, as (section, name, password)"""
    found = []
    for section in ("repos", "groups"):
        objects = full_config.get(section) or {}
        for name, value in objects.items():
            password = value.get("manager_password") if hasattr(value, "get") else None
            if password:
                found.append((section, name, password))
    return found


def check_manager_passwords(found: list) -> None:
    """A manager password set must be given, as --show-config asks it"""
    if not found:
        return
    given = os.environ.get("NPBACKUP_MANAGER_PASSWORD", None)
    if not given:
        names = ", ".join(f"{section}.{name}" for section, name, _ in found)
        raise ExportRefused(
            f"{names} have a manager password: give it in NPBACKUP_MANAGER_PASSWORD", 74
        )
    for section, name, password in found:
        if not hmac.compare_digest(str(password).encode("utf-8"), given.encode("utf-8")):
            # NPF-SEC: sleep to avoid brute force attacks
            sleep(2)
            raise ExportRefused(f"Wrong manager password for {section}.{name}", 74)


def payload(config_file: Path) -> bytes:
    """
    The configuration as this program reads it - its secrets decrypted, an older file
    upgraded, the permissions out of repo_uri, the manager password told only as being
    set - and the file's text as it is on disk, for 4.x to keep its comments. Read through
    a private copy, since the loader rewrites a file it upgrades or whose plaintext secrets
    it encrypts: this one stays as it was
    """
    text = Path(config_file).read_bytes().decode("utf-8")
    work = tempfile.mkdtemp(prefix="npbackup-export-")
    try:
        copy = Path(work) / Path(config_file).name
        shutil.copyfile(config_file, copy)
        try:
            full_config = npbackup.configuration.load_config(copy)
        except SystemExit as exc:
            # The loader exits when it cannot upgrade a file, saying why in the log
            raise ExportRefused(
                f"Cannot read the configuration {config_file}: the log says why", 71
            ) from exc
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if not full_config:
        raise ExportRefused(f"Cannot read the configuration {config_file}", 71)
    # The copy's place is no one's: the configuration's identity is the file's
    full_config.s("uuid", npbackup.configuration.gen_uuid_from_path(config_file))
    found = manager_passwords(full_config)
    check_manager_passwords(found)
    # 4.x has no manager password: that there was one is all it is told
    for section, name, _ in found:
        full_config[section][name]["manager_password"] = True
    document = {"config": full_config, "text": text}
    return json.dumps(document, ensure_ascii=False, default=str).encode("utf-8")


def sealed_export(config_file: Path, public_key: str) -> str:
    """The configuration config_file sealed for public_key, with its headers"""
    config_file = Path(config_file).absolute()
    recipient_key(public_key)
    headers = [
        ("Version", VERSION),
        ("Program", f"{version_dict['name']} {version_dict['version']}"),
        ("Host", platform.node()),
        ("Created", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")),
        ("Configuration", str(config_file)),
    ]
    return seal(public_key, headers, payload(config_file))


def cli_export(config_file: Path, public_key: str) -> int:
    """
    --export-for-4x: the sealed block on stdout and nothing else, what is said on stderr
    and in the log, never what was exported. The exit code
    """
    try:
        if not is_admin():
            raise ExportRefused(
                "Only an administrator may hand the configuration over to NPBackup 4.x"
            )
        block = sealed_export(config_file, public_key)
        _, raw = recipient_key(public_key)
    except ExportRefused as exc:
        logger.critical(f"Cannot hand the configuration over to NPBackup 4.x: {exc}")
        return exc.exit_code
    except EnvironmentError as exc:
        logger.critical(f"Cannot hand the configuration over to NPBackup 4.x: {exc}")
        return 12
    sys.stdout.buffer.write(block.encode("utf-8"))
    sys.stdout.flush()
    logger.info(
        f"Configuration {config_file} handed over to NPBackup 4.x, sealed for key {fingerprint(raw)}"
    )
    return 0
