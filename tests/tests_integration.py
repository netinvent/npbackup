#! /usr/bin/env python3
#  -*- coding: utf-8 -*-


__intname__ = "npbackup_cli_tests"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2026 NetInvent"
__license__ = "BSD-3-Clause"
__build__ = "2026040301"


import os
import sys

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from npbackup.restic_wrapper.url_parser import parse_restic_repo, get_anon_repo_uri

def test_uri_parsing():
    repos = {
        "rest:http://user:pass@localhost:8000/repo": {
            "backend_type": "rest",
            "scheme": "http",
            "username": "user",
            "password": "pass",
            "host": "localhost",
            "port": 8000,
            "path": "/repo",
        },
        "rest:https://user:pass@localhost/repo": {
            "backend_type": "rest",
            "scheme": "https",
            "username": "user",
            "password": "pass",
            "host": "localhost",
            "port": None,
            "path": "/repo",
        },
        "rest:http://user:pass@localhost/repo": {
            "backend_type": "rest",
            "scheme": "http",
            "username": "user",
            "password": "pass",
            "host": "localhost",
            "port": None,
            "path": "/repo",
        },
        "rest:http://localhost/repo": {
            "backend_type": "rest",
            "scheme": "http",
            "username": None,
            "password": None,
            "host": "localhost",
            "port": None,
            "path": "/repo",
        },
        "rest:http://user:pass@localhost:8000/repo%20with%20spaces": {
            "backend_type": "rest",
            "scheme": "http",
            "username": "user",
            "password": "pass",
            "host": "localhost",
            "port": 8000,
            "path": "/repo%20with%20spaces",
        },
        "rest:http://user:pass@localhost:8000/repo%2Fwith%2Fencoded%2Fslashes": {
            "backend_type": "rest",
            "scheme": "http",
            "username": "user",
            "password": "pass",
            "host": "localhost",
            "port": 8000,
            "path": "/repo%2Fwith%2Fencoded%2Fslashes",
        },
        "rest:http://myserver:8888/S0MESH4DYP4TH/npbackup.repo": {
            "backend_type": "rest",
            "scheme": "http",
            "username": None,
            "password": None,
            "host": "myserver",
            "port": 8888,
            "path": "/S0MESH4DYP4TH/npbackup.repo",
        },
        "rest:http://myserver/S0MESH4DYP4TH/npbackup.repo": {
            "backend_type": "rest",
            "scheme": "http",
            "username": None,
            "password": None,
            "host": "myserver",
            "port": None,
            "path": "/S0MESH4DYP4TH/npbackup.repo",
        },
        "rest:https://SOMEGUI:password@mobile.stash.mydomain.tld/somerepo": {
            "backend_type": "rest",
            "scheme": "https",
            "username": "SOMEGUI",
            "password": "password",
            "host": "mobile.stash.mydomain.tld",
            "port": None,
            "path": "/somerepo",
        },
        "rest:https://SOMEGUI:password@mobile.stash.mydomain.tld:1234/somerepo": {
            "backend_type": "rest",
            "scheme": "https",
            "username": "SOMEGUI",
            "password": "password",
            "host": "mobile.stash.mydomain.tld",
            "port": 1234,
            "path": "/somerepo",
        },
        "rest:http+unix:///tmp/rest.socket:/my_backup_repo/": {
            "backend_type": "rest",
            "scheme": "http+unix",
            "username": None,
            "password": None,
            "host": None,
            "port": None,
            "path": "/tmp/rest.socket:/my_backup_repo/",
        },
        "s3:s3.amazonaws.com/mybucket/myrepo": {
            "backend_type": "s3",
            "endpoint": "s3.amazonaws.com",
            "port": None,
            "bucket": "mybucket",
            "path": "myrepo",
        },
        "s3:somehost.tld:9000/bucket/path": {
            "backend_type": "s3",
            "endpoint": "somehost.tld",
            "port": 9000,
            "bucket": "bucket",
            "path": "path",
        },
        "rest:https://user:pass@[::1]:8000/repo": {
            "backend_type": "rest",
            "scheme": "https",
            "username": "user",
            "password": "pass",
            "host": "::1",
            "port": 8000,
            "path": "/repo",
        },
        "sftp:sftp.example.com:/path/to/repo": {
            "backend_type": "sftp",
            "username": None,
            "host": "sftp.example.com",
            "port": None,
            "path": "/path/to/repo",
        },
        "sftp:restic@192.168.254.254:/repo": {
            "backend_type": "sftp",
            "username": "restic",
            "host": "192.168.254.254",
            "port": None,
            "path": "/repo",
        },
        # When using custom ports, we need sftp:// url syntax and :port// format
        "sftp://user@[::1]:2222//srv/restic-repo": {
            "backend_type": "sftp",
            "username": "user",
            "host": "::1",
            "port": 2222,
            "path": "//srv/restic-repo",
        },
        "sftp://user@sftp.example.tld:12345//myrepo": {
            "backend_type": "sftp",
            "username": "user",
            "host": "sftp.example.tld",
            "port": 12345,
            "path": "//myrepo",
        },
        "sftp:restic-backup-host:/srv/restic-repo": {
            "backend_type": "sftp",
            "username": None,
            "host": "restic-backup-host",
            "port": None,
            "path": "/srv/restic-repo",
        },
        "rest:http://user:pass@host:8888/repo": {
            "backend_type": "rest",
            "scheme": "http",
            "username": "user",
            "password": "pass",
            "host": "host",
            "port": 8888,
            "path": "/repo",
        },
        "s3:bucket/path": {
            "backend_type": "s3",
            "endpoint": None,
            "bucket": "bucket",
            "path": "path",
        },
        "b2:bucket/path": {"backend_type": "b2", "bucket": "bucket", "path": "path"},
        "azure:container/path": {
            "backend_type": "azure",
            "container": "container",
            "path": "path",
        },
        "rclone:remote:subpath": {
            "backend_type": "rclone",
            "remote": "remote",
            "path": "subpath",
        },
        "/local/path": {"backend_type": "local", "path": "/local/path"},
    }

    for repo in repos:
        repo_info = parse_restic_repo(repo)
        expected_info = repos[repo]
        print("REPO    ", repo_info)
        print("EXPECTED", expected_info)
        assert repo_info == expected_info


def test_anon_uri_generation():
    repos = {
        "rest:http://user:pass@localhost:8000/repo": "rest:http://user:___[o_0]___@localhost:8000/repo",
        "rest:https://user:pass@localhost/repo": "rest:https://user:___[o_0]___@localhost/repo",
        "rest:http://user:pass@localhost/repo": "rest:http://user:___[o_0]___@localhost/repo",
        "rest:http://localhost/repo": "rest:http://localhost/repo",
        "rest:http://user:pass@localhost:8000/repo%20with%20spaces": "rest:http://user:___[o_0]___@localhost:8000/repo%20with%20spaces",
        "rest:http://user:pass@localhost:8000/repo%2Fwith%2Fencoded%2Fslashes": "rest:http://user:___[o_0]___@localhost:8000/repo%2Fwith%2Fencoded%2Fslashes",
        "rest:http://myserver:8888/S0MESH4DYP4TH/npbackup.repo": "rest:http://myserver:8888/S0MESH4DYP4TH/npbackup.repo",
        "rest:http://myserver/S0MESH4DYP4TH/npbackup.repo": "rest:http://myserver/S0MESH4DYP4TH/npbackup.repo",
    }

    for repo, expected_anon_uri in repos.items():
        _, anon_uri = get_anon_repo_uri(repo)
        print(f"Original URI: {repo}")
        print(f"Expected Anon URI: {expected_anon_uri}")
        print(f"Generated Anon URI: {anon_uri}")
        assert anon_uri == expected_anon_uri, f"Anon URI mismatch for {repo}"

if __name__ == "__main__":
    test_uri_parsing()
    test_anon_uri_generation()