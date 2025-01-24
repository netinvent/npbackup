#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.upgrade_server.api"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023-2025 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2025011401"
__appname__ = "npbackup.upgrader"


import os
from typing import Optional, Union
import logging
import secrets
from argparse import ArgumentParser
from fastapi import FastAPI, HTTPException, Response, Depends, status, Request, Header
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi_offline import FastAPIOffline
from ofunctions.logger_utils import logger_get_logger
from upgrade_server.models.files import (
    ClientTargetIdentification,
    FileGet,
    FileSend,
    Platform,
    Arch,
    BuildType,
    Audience,
    Artefact,
)
from upgrade_server.models.oper import CurrentVersion
import upgrade_server.crud as crud
import upgrade_server.configuration as configuration
from upgrade_server.__debug__ import _DEBUG


# Make sure we load given config files again
parser = ArgumentParser()
parser.add_argument(
    "-c",
    "--config-file",
    dest="config_file",
    type=str,
    default=None,
    required=False,
    help="Path to upgrade_server.conf file",
)

parser.add_argument(
    "--log-file",
    type=str,
    default=None,
    required=False,
    help="Optional path for logfile, overrides config file values",
)

args = parser.parse_args()


if args.log_file:
    log_file = args.log_file
else:
    if os.name == "nt":
        log_file = os.path.join(f"{__appname__}.log")
    else:
        log_file = f"/var/log/{__appname__}.log"
logger = logger_get_logger(log_file, debug=_DEBUG)


if args.config_file:
    config_dict = configuration.load_config(args.config_file)
else:
    config_dict = configuration.load_config()

try:
    if not args.log_file:
        logger = logger_get_logger(config_dict["http_server"]["log_file"], debug=_DEBUG)
except (AttributeError, KeyError, IndexError, TypeError):
    pass


#### Create app
# app = FastAPI()        # standard FastAPI initialization
app = (
    FastAPIOffline()
)  # Offline FastAPI initialization, allows /docs to not use online CDN
security = HTTPBasic()


def get_current_username(credentials: HTTPBasicCredentials = Depends(security)):
    authenticated_user = None

    for user in config_dict["http_server"]["users"]:
        try:
            if secrets.compare_digest(
                credentials.username.encode("utf-8"),
                user.get("username").encode("utf-8"),
            ):
                if secrets.compare_digest(
                    credentials.password.encode("utf-8"),
                    user.get("password").encode("utf-8"),
                ):
                    authenticated_user = user
                    break
        except Exception as exc:
            logger.info(f"Failed to check user: {exc}")

    if authenticated_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def get_user_permissions(username: str):
    """
    Returns a list of permissions
    """
    try:
        for user in config_dict["http_server"]["users"]:
            if user.get("username") == username:
                return user.get("permissions")
    except Exception as exc:
        logger.error(f"Failed to get user permissions from configuration file: {exc}")
        logger.debug("Trace", exc_info=True)
    return []


@app.get("/")
async def api_root(auth=Depends(get_current_username)):
    if crud.is_enabled(config_dict):
        return {
            "app": __appname__,
        }
    else:
        return {"app": __appname__, "maintenance": "enabled"}


@app.get("/status")
async def api_status():
    if crud.is_enabled(config_dict):
        return {
            "app": "running",
        }
    else:
        return {"app": __appname__, "maintenance": "enabled"}


@app.get(
    "/current_version/{platform}/{arch}/{build_type}/{audience}",
    response_model=CurrentVersion,
    status_code=200,
)
@app.get(
    "/current_version/{platform}/{arch}/{build_type}/{audience}/{auto_upgrade_host_identity}",
    response_model=CurrentVersion,
    status_code=200,
)
@app.get(
    "/current_version/{platform}/{arch}/{build_type}/{audience}/{auto_upgrade_host_identity}/{installed_version}",
    response_model=CurrentVersion,
    status_code=200,
)
@app.get(
    "/current_version/{platform}/{arch}/{build_type}/{audience}/{auto_upgrade_host_identity}/{installed_version}/{group}",
    response_model=CurrentVersion,
    status_code=200,
)
async def current_version(
    request: Request,
    platform: Platform,
    arch: Arch,
    build_type: BuildType,
    audience: Audience,
    auto_upgrade_host_identity: str = None,
    installed_version: str = None,
    group: str = None,
    x_real_ip: Optional[str] = Header(default=None),
    x_forwarded_for: Optional[str] = Header(default=None),
    referer: Optional[str] = Header(default=None),
    auth=Depends(get_current_username),
):
    if x_real_ip:
        client_ip = x_real_ip
    elif x_forwarded_for:
        client_ip = x_forwarded_for
    else:
        client_ip = request.client.host

    try:
        has_permission = (
            True
            if audience.value in get_user_permissions(auth).get("audience")
            else False
        )
    except Exception as exc:
        logger.error(f"Failed to get user permissions (1): {exc}")
        has_permission = False

    data = {
        "action": "check_version",
        "ip": client_ip,
        "user": auth,
        "has_permission": has_permission,
        "auto_upgrade_host_identity": auto_upgrade_host_identity,
        "installed_version": installed_version,
        "group": group,
        "artefact": None,
        "platform": platform.value,
        "arch": arch.value,
        "build": build_type.value,
        "audience": audience.value,
    }

    try:
        crud.store_host_info(config_dict["upgrades"]["statistics_file"], host_id=data)
    except KeyError:
        logger.error("No statistics file set.")

    if not has_permission:
        raise HTTPException(
            status_code=403,
            detail="User does not have permission to access this resource",
        )

    if not crud.is_enabled(config_dict):
        return CurrentVersion(version="0.00")

    try:
        target_id = ClientTargetIdentification(
            platform=platform,
            arch=arch,
            build_type=build_type,
            audience=audience,
            auto_upgrade_host_identity=auto_upgrade_host_identity,
            installed_version=installed_version,
            group=group,
        )
        result = crud.get_current_version(config_dict, target_id)
        if not result:
            raise HTTPException(status_code=404, detail="Not found")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Cannot get version file: {}".format(exc), exc_info=True)
        raise HTTPException(
            status_code=400,
            detail="Cannot get version file: {}".format(exc),
        )


@app.get(
    "/info/{artefact}/{platform}/{arch}/{build_type}/{audience}",
    response_model=Union[FileSend, dict],
    status_code=200,
)
@app.get(
    "/info/{artefact}/{platform}/{arch}/{build_type}/{audience}/{auto_upgrade_host_identity}",
    response_model=Union[FileSend, dict],
    status_code=200,
)
@app.get(
    "/info/{artefact}/{platform}/{arch}/{build_type}/{audience}/{auto_upgrade_host_identity}/{installed_version}",
    response_model=Union[FileSend, dict],
    status_code=200,
)
@app.get(
    "/info/{artefact}/{platform}/{arch}/{build_type}/{audience}/{auto_upgrade_host_identity}/{installed_version}/{group}",
    response_model=Union[FileSend, dict],
    status_code=200,
)
async def upgrades(
    request: Request,
    artefact: Artefact,
    platform: Platform,
    arch: Arch,
    build_type: BuildType,
    audience: Audience,
    auto_upgrade_host_identity: str = None,
    installed_version: str = None,
    group: str = None,
    x_real_ip: Optional[str] = Header(default=None),
    x_forwarded_for: Optional[str] = Header(default=None),
    auth=Depends(get_current_username),
):
    if x_real_ip:
        client_ip = x_real_ip
    elif x_forwarded_for:
        client_ip = x_forwarded_for
    else:
        client_ip = request.client.host

    try:
        has_permission = (
            True
            if audience.value in get_user_permissions(auth).get("audience")
            else False
        )
    except Exception as exc:
        logger.error(f"Failed to get user permissions (2): {exc}")
        has_permission = False

    data = {
        "action": "get_file_info",
        "ip": client_ip,
        "user": auth,
        "has_permission": has_permission,
        "auto_upgrade_host_identity": auto_upgrade_host_identity,
        "installed_version": installed_version,
        "group": group,
        "artefact": artefact.value,
        "platform": platform.value,
        "arch": arch.value,
        "build": build_type.value,
        "audience": audience.value,
    }

    try:
        crud.store_host_info(config_dict["upgrades"]["statistics_file"], host_id=data)
    except KeyError:
        logger.error("No statistics file set.")

    if not has_permission:
        raise HTTPException(
            status_code=403,
            detail="User does not have permission to access this resource",
        )

    if not crud.is_enabled(config_dict):
        raise HTTPException(
            status_code=503, detail="Service is currently disabled for maintenance"
        )

    file = FileGet(
        artefact=artefact,
        platform=platform,
        arch=arch,
        build_type=build_type,
        audience=audience,
        auto_upgrade_host_identity=auto_upgrade_host_identity,
        installed_version=installed_version,
        group=group,
    )
    try:
        result = crud.get_file(config_dict, file)
        if not result:
            raise HTTPException(status_code=404, detail="Not found")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.debug("Cannot get file info: {}".format(exc), exc_info=True)
        raise HTTPException(
            status_code=400,
            detail="Cannot get file info: {}".format(exc),
        )


@app.get(
    "/download/{artefact}/{platform}/{arch}/{build_type}/{audience}",
    response_model=FileSend,
    status_code=200,
)
@app.get(
    "/download/{artefact}/{platform}/{arch}/{build_type}/{audience}/{auto_upgrade_host_identity}",
    response_model=FileSend,
    status_code=200,
)
@app.get(
    "/download/{artefact}/{platform}/{arch}/{build_type}/{audience}/{auto_upgrade_host_identity}/{installed_version}",
    response_model=FileSend,
    status_code=200,
)
@app.get(
    "/download/{artefact}/{platform}/{arch}/{build_type}/{audience}/{auto_upgrade_host_identity}/{installed_version}/{group}",
    response_model=FileSend,
    status_code=200,
)
async def download(
    request: Request,
    artefact: Artefact,
    platform: Platform,
    arch: Arch,
    build_type: BuildType,
    audience: Audience,
    auto_upgrade_host_identity: str = None,
    installed_version: str = None,
    group: str = None,
    x_real_ip: Optional[str] = Header(default=None),
    x_forwarded_for: Optional[str] = Header(default=None),
    auth=Depends(get_current_username),
):
    if x_real_ip:
        client_ip = x_real_ip
    elif x_forwarded_for:
        client_ip = x_forwarded_for
    else:
        client_ip = request.client.host

    try:
        has_permission = (
            True
            if audience.value in get_user_permissions(auth).get("audience")
            else False
        )
    except Exception as exc:
        logger.error(f"Failed to get user permissions (3): {exc}")
        has_permission = False

    data = {
        "action": "download_upgrade",
        "ip": client_ip,
        "user": auth,
        "has_permission": has_permission,
        "auto_upgrade_host_identity": auto_upgrade_host_identity,
        "installed_version": installed_version,
        "group": group,
        "artefact": artefact.value,
        "platform": platform.value,
        "arch": arch.value,
        "build": build_type.value,
        "audience": audience.value,
    }

    try:
        crud.store_host_info(config_dict["upgrades"]["statistics_file"], host_id=data)
    except KeyError:
        logger.error("No statistics file set.")

    if not has_permission:
        raise HTTPException(
            status_code=403,
            detail="User does not have permission to access this resource",
        )

    if not crud.is_enabled(config_dict):
        raise HTTPException(
            status_code=503, detail="Service is currently disabled for maintenance"
        )

    file = FileGet(
        artefact=artefact,
        platform=platform,
        arch=arch,
        build_type=build_type,
        audience=audience,
        auto_upgrade_host_identity=auto_upgrade_host_identity,
        installed_version=installed_version,
        group=group,
    )
    try:
        result = crud.get_file(config_dict, file, content=True)
        if not result:
            raise HTTPException(status_code=404, detail="Not found")
        headers = {"Content-Disposition": 'attachment; filename="npbackup"'}
        return Response(content=result, media_type="application/dat", headers=headers)
    except HTTPException:
        raise
    except Exception as exc:
        logger.debug("Cannot get file for download: {}".format(exc), exc_info=True)
        raise HTTPException(
            status_code=400,
            detail="Cannot get file for download: {}".format(exc),
        )
