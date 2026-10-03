# Backup Proof

**Find missing and different file contents before a file-copy backup is needed.**

A backup job finishes successfully, but its copied files may be old, excluded unexpectedly, or different from the intended recovery point. File count, size, and timestamps alone cannot establish that the data matches.

Backup Proof reads each included regular file in the source and backup trees, computes SHA-256, and produces an actionable local report. It never repairs, copies, or deletes data.

## Try the demo

Requires Python 3.11 or newer. No pip packages. Run from this repository directory:

```sh
python backup_proof.py --demo
```

Open `reports/backup-proof.html`. The tiny fictional trees include a matching file, a missing file, outdated contents, and retained history. Exit code **1** is expected for this deliberately imperfect backup.

[Included fictional example report](docs/demo-report.html)

## Audit your own file-copy backup

Use quiet data or a mounted point-in-time snapshot. Choose non-overlapping directory trees and put reports outside both:

```powershell
python .\backup_proof.py --source "D:\LabSource" --backup "E:\LabBackup" --output ".\reports\lab-audit"
```

```sh
python backup_proof.py --source /mnt/lab-source --backup /mnt/lab-backup --output reports/lab-audit
```

Compare the **intended recovery point**, not a busy live source against yesterday's backup. Otherwise legitimate changes will look like discrepancies. This tool compares unencrypted, directly accessible regular files; backup archives, encrypted repositories, compressed proprietary formats, and database-native backups require their own verification/restore tools.

Optional exclusions apply equally to both trees:

```sh
python backup_proof.py --source lab-source --backup lab-backup --exclude "*.tmp" --exclude "cache" --output reports/lab-audit
```

Exclusions are case-sensitive glob matches on forward-slash relative paths. `cache` skips that exact directory and its descendants; `*.tmp` matches matching paths including nested ones under Python's `fnmatchcase` semantics. Every excluded path and pattern is disclosed in the JSON. A directory excluded at its root is listed once; its contents are not enumerated or audited.

## Read the evidence

| Finding | What it establishes | What to do |
|---|---|---|
| Missing | A source path has no matching backup path | Review backup scope and the intended recovery point |
| Mismatch | SHA-256 or file size differs | Check age, consistency, and content before replacing anything |
| Extra | Backup has a path absent from current source | May be retained history; review policy rather than deleting it |
| Unverified | Permission, changing data, links, or another gap prevented full verification | Resolve the gap and rerun |
| Verified | Included regular file paths and contents matched in this audit | Follow with a separate restore drill and application test |

An empty source, unreadable file, changing tree, symbolic link/junction, case-colliding filename, or source/backup hard link cannot produce a full `verified` result. The default is a strict file-tree comparison: extras require review even if all source files match.

## Why full hashing?

Two files can have equal sizes and timestamps yet different contents. Full SHA-256 comparison catches that condition; sampling could miss corruption elsewhere in a file. File reads use bounded 1 MiB chunks rather than loading entire files into memory. The manifests record size and hash for each successfully read file.

The tool checks metadata around hashing and inventories both trees again afterward. Changes invalidate completeness. This helps catch concurrent writes, but it is not an atomic snapshot and cannot defeat all concurrent or adversarial filesystem changes.

## Limits that matter

- File contents only: no ACLs, ownership, NTFS alternate data streams, extended attributes, directory metadata, or empty-directory verification.
- No database/PST/application-consistency guarantee. Quiesce applications or use approved snapshot/native backup tools. A byte-identical live database copy can still be unusable.
- No restore simulation, recovery-time estimate, immutable storage check, encryption check, or independent off-site storage proof.
- Full reads can be expensive. Time is approximately the time to read both included trees; run a small lab first and schedule production audits appropriately.
- Hashes are compared with the current source, not a signed trusted manifest. An unintended change replicated into both trees can match.
- No root directory paths are embedded in reports, but relative filenames and hashes can still be confidential.

## Validate and learn

```sh
python -m unittest discover -s tests -v
```

Tests cover equal-size/equal-timestamp corruption, missing/extra files, excluded scope, empty input, unreadable data, concurrent additions, overlapping roots, symlinks, hard links, and case collisions. Tests that require unsupported filesystem features are skipped explicitly on that platform.

See [WALKTHROUGH.md](WALKTHROUGH.md) for a lab. GitHub Actions is configured for Windows/Linux and Python 3.11/3.12; remote results are confirmed only after execution.

## References

- [Python hashlib documentation](https://docs.python.org/3/library/hashlib.html)
- [Python filesystem/stat documentation](https://docs.python.org/3/library/os.html)
- [Python glob matching semantics](https://docs.python.org/3/library/fnmatch.html)

MIT licensed. Initial implementation prepared with AI assistance for Raihan Mahmud's learning portfolio. No production deployment or recovery success is claimed.
