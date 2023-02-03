#! /usr/bin/env python3
#  -*- coding: utf-8 -*-

__intname__ = "npbackup.upgrade_server.api"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023020301"
__appname__ = "npbackup.upgrader"


from typing import Literal
import logging
import secrets
from fastapi import FastAPI, HTTPException, Response, Depends, status, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi_offline import FastAPIOffline
from upgrade_server.models.files import FileGet, FileSend, Platform, Arch
from upgrade_server.models.oper import CurrentVersion
import upgrade_server.crud as crud
import upgrade_server.configuration as configuration


config_dict = configuration.load_config()
logger = logging.getLogger()

#### Create app
# app = FastAPI()        # standard FastAPI initialization
app = (
    FastAPIOffline()
)  # Offline FastAPI initialization, allows /docs to not use online CDN
security = HTTPBasic()


def get_current_username(credentials: HTTPBasicCredentials = Depends(security)):
    current_username_bytes = credentials.username.encode("utf8")
    correct_username_bytes = config_dict["http_server"]["username"].encode("utf-8")
    is_correct_username = secrets.compare_digest(
        current_username_bytes, correct_username_bytes
    )
    current_password_bytes = credentials.password.encode("utf8")
    correct_password_bytes = config_dict["http_server"]["password"].encode("utf-8")
    is_correct_password = secrets.compare_digest(
        current_password_bytes, correct_password_bytes
    )
    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


@app.get("/")
async def api_root(auth=Depends(get_current_username)):
    if crud.is_enabled():
        return {
            "app": __appname__,
        }
    else:
        return {"app": "Currently under maintenance"}


@app.get("/current_version", response_model=CurrentVersion, status_code=200)
async def current_version(request: Request, auth=Depends(get_current_username)):
    data = {
        "action": "check_version",
        "ip": request.client.host,
        "auto_upgrade_host_identity": "",
        "installed_version": "",
        "group": "",
        "platform": "",
        "arch": "",
    }

    try:
        crud.store_host_info(config_dict["upgrades"]["statistics_file"], host_id=data)
    except KeyError:
        logger.error("No statistics file set.")
    try:
        result = crud.get_current_version()
        if not result:
            raise HTTPException(status_code=404, detail="Not found")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.debug("Cannot get file: {}".format(exc), exc_info=True)
        raise HTTPException(
            status_code=400,
            detail="Cannot get file: {}".format(exc),
        )


@app.get("/upgrades/{platform}/{arch}", response_model=FileSend, status_code=200)
@app.get(
    "/upgrades/{platform}/{arch}/{auto_upgrade_host_identity}",
    response_model=FileSend,
    status_code=200,
)
@app.get(
    "/upgrades/{platform}/{arch}/{auto_upgrade_host_identity}/{installed_version}",
    response_model=FileSend,
    status_code=200,
)
@app.get(
    "/upgrades/{platform}/{arch}/{auto_upgrade_host_identity}/{installed_version}/{group}",
    response_model=FileSend,
    status_code=200,
)
async def upgrades(
    request: Request,
    platform: Platform,
    arch: Arch,
    auto_upgrade_host_identity: str = None,
    installed_version: str = None,
    group: str = None,
    auth=Depends(get_current_username),
):
    data = {
        "action": "get_file_info",
        "ip": request.client.host,
        "auto_upgrade_host_identity": auto_upgrade_host_identity,
        "installed_version": installed_version,
        "group": group,
        "platform": platform.value,
        "arch": arch.value,
    }

    try:
        crud.store_host_info(config_dict["upgrades"]["statistics_file"], host_id=data)
    except KeyError:
        logger.error("No statistics file set.")

    file = FileGet(platform=platform, arch=arch)
    try:
        result = crud.get_file(file)
        if not result:
            raise HTTPException(status_code=404, detail="Not found")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.debug("Cannot get file: {}".format(exc), exc_info=True)
        raise HTTPException(
            status_code=400,
            detail="Cannot get file: {}".format(exc),
        )


@app.get(
    "/download/{platform}/{arch}/{auto_upgrade_host_identity}/{installed_version}/{group}",
    response_model=FileSend,
    status_code=200,
)
async def download(
    request: Request,
    platform: Platform,
    arch: Arch,
    auto_upgrade_host_identity: str = None,
    installed_version: str = None,
    group: str = None,
    auth=Depends(get_current_username),
):
    data = {
        "action": "download_upgrade",
        "ip": request.client.host,
        "auto_upgrade_host_identity": auto_upgrade_host_identity,
        "installed_version": installed_version,
        "group": group,
        "platform": platform.value,
        "arch": arch.value,
    }

    try:
        crud.store_host_info(config_dict["upgrades"]["statistics_file"], host_id=data)
    except KeyError:
        logger.error("No statistics file set.")
    file = FileGet(platform=platform, arch=arch)
    try:
        result = crud.get_file(file, content=True)
        if not result:
            raise HTTPException(status_code=404, detail="Not found")
        headers = {"Content-Disposition": 'attachment; filename="npbackup"'}
        return Response(content=result, media_type="application/dat", headers=headers)
    except HTTPException:
        raise
    except Exception as exc:
        logger.debug("Cannot get file: {}".format(exc), exc_info=True)
        raise HTTPException(
            status_code=400,
            detail="Cannot get file: {}".format(exc),
        )
