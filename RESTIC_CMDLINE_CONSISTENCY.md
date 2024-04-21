## List of various restic problems encountered while developping NPBackup

As of 2024/01/02, version 0.16.2:

### json inconsistencies

- `restic check --json` does not produce json output, probably single str on error
- `restic unlock --json` does not produce any output, probably single str on error
- `restic repair index --json` does not produce json output
```
loading indexes...
getting pack files to read...
rebuilding index
[0:00] 100.00%  28 / 28 packs processed
deleting obsolete index files
done
```
- `restic repair snapshots --json` does not produce json output
```
snapshot 00ecc4e3 of [c:\git\npbackup] at 2024-01-02 19:15:35.3779691 +0100 CET)

snapshot 1066f045 of [c:\git\npbackup] at 2023-12-28 13:46:41.3639521 +0100 CET)

no snapshots were modified
```
- `restic forget <snapshot-id> --json` does not produce any output, and produces str output on error. Example on error:
```
Ignoring "ff20970b": no matching ID found for prefix "ff20970b"
```
- `restic list index|blobs|snapshots --json` produce one result per line output, not json, example for blobs:
```
tree 0d2eef6a1b06aa0650a08a82058d57a42bf515a4c84bf4f899e391a4b9906197
tree 9e61b5966a936e2e8b4ef4198b86ad59000c5cba3fc6250ece97cb13621b3cd1
tree 1fe90879bd35d90cd4fde440e64bfc16b331297cbddb776a43eb3fdf94875540
```

- `restic key list --json` produces direct parseable json
- `restic stats --json` produces direct parseable json
- `restic find <path> --json` produces direct parseable json
- `restic snapshots --json` produces direct parseable json
- `restic backup --json` produces multiple state lines, each one being valid json, which makes sense
- `restic restore <snapshot> --target <target> --json` produces multiple state lines, each one being valid json, which makes sense

### backup results inconsistency

When using `restic backup`, we get different results depending on if we're using `--json`or not:

- "data_blobs": Not present in string output
- "tree_blobs": Not present in string output
- "data_added": Present in both outputs, is "4.425" in `Added to the repository: 4.425 MiB (1.431 MiB stored)`
- "data_stored":  Not present in json output, is "1.431" in `Added to the repository: 4.425 MiB (1.431 MiB stored)`

`restic backup` results
```
repository 962d5924 opened (version 2, compression level auto)
using parent snapshot 325a2fa1
[0:00] 100.00%  4 / 4 index files loaded

Files:         216 new,    21 changed,  5836 unmodified
Dirs:           29 new,    47 changed,   817 unmodified
Added to the repository: 4.425 MiB (1.431 MiB stored)

processed 6073 files, 116.657 MiB in 0:03
snapshot b28b0901 saved
```

`restic backup --json` results
```
{"message_type":"summary","files_new":5,"files_changed":15,"files_unmodified":6058,"dirs_new":0,"dirs_changed":27,"dirs_unmodified":866,"data_blobs":17,"tree_blobs":28,"data_added":281097,"total_files_processed":6078,"total_bytes_processed":122342158,"total_duration":1.2836983,"snapshot_id":"360333437921660a5228a9c1b65a2d97381f0bc135499c6e851acb0ab84b0b0a"}
```