"""Read-only, content-based audit of a source tree against a file-copy backup."""
import argparse
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from report import write_report


def signature(s):
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def is_link(path):
    return path.is_symlink() or (hasattr(os.path, 'isjunction') and os.path.isjunction(path))


def inventory(root, excludes):
    files, issues, excluded = {}, [], []

    def walk(directory):
        try:
            with os.scandir(directory) as entries:
                ordered = sorted(entries, key=lambda x: x.name)
        except OSError as exc:
            issues.append({'path': directory.relative_to(root).as_posix(), 'reason': str(exc)})
            return
        for entry in ordered:
            path = Path(entry.path)
            relative = path.relative_to(root).as_posix()
            if any(fnmatch.fnmatchcase(relative, pattern) for pattern in excludes):
                excluded.append(relative)
                continue
            try:
                if is_link(path):
                    issues.append({'path': relative, 'reason': 'Symbolic link or junction not followed'})
                else:
                    # Windows DirEntry.stat() omits file identity. Use the same
                    # full, non-following metadata API as the hashing checks.
                    info = path.lstat()
                    if stat.S_ISDIR(info.st_mode):
                        walk(path)
                    elif stat.S_ISREG(info.st_mode):
                        files[relative] = signature(info)
                    else:
                        issues.append({'path': relative, 'reason': 'Not a regular file; cannot verify'})
            except OSError as exc:
                issues.append({'path': relative, 'reason': str(exc)})
    walk(root)
    folded = {}
    for name in files:
        folded.setdefault(name.casefold(), []).append(name)
    for names in folded.values():
        if len(names) > 1:
            issues.append({'path': ', '.join(names), 'reason': 'Case-colliding names may not restore to a case-insensitive filesystem'})
    return files, issues, excluded


def digest(path, expected):
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or signature(before) != expected or is_link(path):
            raise OSError('File changed or became a link before hashing')
        hasher = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(block)
        if signature(os.fstat(stream.fileno())) != expected or signature(path.lstat()) != expected or is_link(path):
            raise OSError('File changed while hashing')
        return hasher.hexdigest()


def validate_roots(source, backup, output=None):
    # Resolving catches aliasing through symlinked parents. Overlapping roots
    # cannot establish whether a separate backup has the required files.
    source, backup = Path(source).resolve(strict=True), Path(backup).resolve(strict=True)
    if not source.is_dir() or not backup.is_dir():
        raise ValueError('Source and backup must be directories')
    if source == backup or source in backup.parents or backup in source.parents:
        raise ValueError('Source and backup must be separate, non-overlapping trees')
    if output:
        for suffix in ('.html', '.json'):
            destination = Path(output).with_suffix(suffix).resolve()
            if destination == source or source in destination.parents or destination == backup or backup in destination.parents:
                raise ValueError('Report output must be outside both audited trees')
    return source, backup


def audit(source, backup, excludes=(), output=None):
    source, backup = validate_roots(source, backup, output)
    before = {}
    manifests = {}
    problems = []
    excluded = {}
    for label, root in (('source', source), ('backup', backup)):
        files, issues, omitted = inventory(root, excludes)
        before[label] = files
        excluded[label] = omitted
        problems.extend({'tree': label, **item} for item in issues)
        manifests[label] = {}
        for name, info in files.items():
            try:
                manifests[label][name] = {'size_bytes': info[2], 'sha256': digest(root / name, info)}
            except OSError as exc:
                problems.append({'tree': label, 'path': name, 'reason': str(exc)})
    # A second inventory detects additions/removals and changes after an early
    # file was hashed. It does not replace an atomic filesystem snapshot.
    for label, root in (('source', source), ('backup', backup)):
        current, issues, _ = inventory(root, excludes)
        problems.extend({'tree': label, **item} for item in issues)
        if current != before[label]:
            problems.append({'tree': label, 'path': '.', 'reason': 'Tree changed during audit; rerun against a quiet tree or snapshot'})
    if not before['source']:
        problems.append({'tree': 'source', 'path': '.', 'reason': 'No included source files; an empty comparison cannot verify a backup'})
    findings = []
    matched = 0
    for name in sorted(set(before['source']) | set(before['backup'])):
        if name not in before['backup']:
            findings.append({'status': 'missing', 'item': name, 'evidence': 'Source file has no matching backup path.', 'next_step': 'Review backup scope/exclusions and copy this file with your backup process.'})
        elif name not in before['source']:
            findings.append({'status': 'extra', 'item': name, 'evidence': 'Backup path does not exist in the current source.', 'next_step': 'May be retained history; review your retention policy. Nothing is deleted.'})
        elif before['source'][name][:2] == before['backup'][name][:2] and before['source'][name][1] != 0:
            problems.append({'tree': 'both', 'path': name, 'reason': 'Source and backup reference the same filesystem object (hard link); independent copy not established'})
        elif name not in manifests['source'] or name not in manifests['backup']:
            continue
        elif manifests['source'][name] != manifests['backup'][name]:
            findings.append({'status': 'mismatch', 'item': name, 'evidence': 'SHA-256 content or size differs. Matching filenames/timestamps would not establish equality.', 'next_step': 'Check backup age and intended recovery point before replacing anything.'})
        else:
            matched += 1
    problems = list({json.dumps(p, sort_keys=True): p for p in problems}.values())
    for problem in problems:
        findings.append({'status': 'unverified', 'item': f"{problem['tree']}/{problem['path']}", 'evidence': problem['reason'], 'next_step': 'Resolve unreadable or changing data and rerun; do not treat this audit as complete.'})
    status = 'incomplete' if problems else ('attention' if findings else 'verified')
    if not findings:
        findings.append({'status': 'verified', 'item': 'Included file contents', 'evidence': f'{matched} files have matching SHA-256 hashes and sizes.', 'next_step': 'Next, perform a separate restore drill and test application usability. ACLs and application consistency were not verified.'})
    return {'schema_version': 1, 'timestamp': datetime.now(timezone.utc).isoformat(), 'status': status, 'summary': f'{matched} matching files; {len(problems)} verification gaps. This compares included regular file contents, not a complete recovery test.', 'findings': findings, 'counts': {'source_files': len(before['source']), 'backup_files': len(before['backup']), 'matched': matched}, 'exclusion_patterns': list(excludes), 'excluded_paths': excluded, 'manifests': manifests, 'issues': problems}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path)
    p.add_argument('--backup', type=Path)
    p.add_argument('--exclude', action='append', default=[], help='Case-sensitive glob on the relative POSIX path; applied equally to both trees')
    p.add_argument('--demo', action='store_true', help='Compare the tiny fictional example trees')
    p.add_argument('--output', default='reports/backup-proof')
    args = p.parse_args()
    if args.demo:
        if args.source or args.backup:
            p.error('Use --demo or a --source/--backup pair')
        args.source = Path(__file__).parent / 'examples/source'
        args.backup = Path(__file__).parent / 'examples/backup'
    elif not args.source or not args.backup:
        p.error('Both --source and --backup are required')
    try:
        result = audit(args.source, args.backup, args.exclude, args.output)
        if args.demo: result['demo'] = True
        report = write_report(result, args.output, 'Backup Proof')
        print(f"{result['status'].upper()}: {report}")
        return 0 if result['status'] == 'verified' else (2 if result['status'] == 'incomplete' else 1)
    except (OSError, ValueError, TypeError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
