# Learn and demonstrate it

## A 20-minute lab

1. Run the included demo and identify the matching, missing, mismatch, and extra-file cases.
2. Create two separate temporary lab directories. Put an identical text file in both and audit them; the result should be verified for included file contents.
3. Change a word in the backup copy without changing its length. Observe that hashing still detects a mismatch.
4. Add a new source file. Observe the missing-path finding.
5. Add an old backup-only note. Observe the extra-path finding; verify that nothing was deleted.
6. Run the tests and read the equal-size/equal-timestamp case. Explain why checking metadata alone would miss it.

Keep all experiments on disposable lab data. The tool itself is read-only; manual file edits in this lab are yours.

## Read the implementation in this order

`validate_roots()` rejects overlapping trees and report destinations inside audited data. `inventory()` determines explicit scope and records verification gaps. `digest()` hashes streaming contents and checks metadata around the read. `audit()` compares manifests, rechecks inventories, and prevents false success when evidence is incomplete.

## Explain your work honestly

“I worked on a file-copy backup audit that compares SHA-256 contents and flags missing, different, extra, or unverified files. It can catch differences hidden by matching size and timestamps. It does not establish application consistency, preserved permissions, or successful restore.”

## A useful next contribution

Add a manifest saved at the backup's intended recovery point, with explicit provenance and versioning. Keep current-source comparison available as a separate mode. Then write a controlled restore drill in a disposable directory and record application usability separately.
