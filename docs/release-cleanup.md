# Cleanup after the next published package

This is a preparation plan, not permission to delete work now. No files have been
removed by this review. Publication, a clean installation check and a usable
rollback image must come first.

## What we can remove later

| Files | Required checks before removal |
| --- | --- |
| Exported image archives used by the scanner | Final reports and exact image digest retained; published image available and verified. |
| Scanner database/cache copies | Scan finished; reports retained. The database can be downloaded again. |
| Old extracted build contexts and duplicate package tar files | No build is using them; final package/source materials retained elsewhere and checksummed. |
| Generated installation/cancellation fixtures | Tests finished; receipts, source/output hashes and logs retained. No library media in the directory. |
| Superseded MuxMender research images/containers | All container references checked, stopped research work only, current app and rollback images protected. |
| Temporary code-only source review drafts | Approved canonical source materials and review records retained. Source/license review is still open, so these stay for now. |

The inspected TrueNAS release/research folders occupy roughly 2.4 GiB, excluding
Docker images/cache. About 1.1 GiB is exported scanner input and scanner cache;
extracted build contexts occupy about 244 MiB. These are potential cleanup targets,
not reclaimed space. Local copies include roughly 1 GiB of a transformed source
review draft, which remains protected until the final source materials are approved.

## What stays

- Library media and both production mounts, including history/recovery records.
- Current app, published release and one verified rollback image.
- Exact corresponding sources, third-party notices, build recipes and checksums
  required for the released image. Do not delete them just because a build passed.
- Final software inventory, security reports, test receipts and compact logs.
- Active or unresolved research work, failed cases still under investigation,
  and anything whose owner or purpose is uncertain.
- Repository regression tests. Old test **outputs** can be removed; regression
  code stays unless separately reviewed as obsolete.

## Execution order

1. Verify publication, installation and rollback; record their exact digests.
2. Run the read-only `deploy/truenas/inventory-release-storage.sh` on TrueNAS.
   Container image references must be known before removing any image tag.
3. Copy the final compact evidence to retained storage and verify its checksums.
4. Produce an exact-path deletion list from that inventory. Check that each path
   stays inside its intended research/build directory and is not linked into a
   media mount. Stop if a job is active or recovery is unresolved.
5. Remove only the reviewed targets. Do not use broad system/image/volume prune
   commands; this host also runs other applications.
6. Compare filesystem and pool free space. ZFS snapshots and shared Docker layers
   can retain blocks, so deleted logical bytes are not a space-reclaimed receipt.

The app's normal temporary-file policy is separate: see
[post-task cleanup](post-task-cleanup.md). Release maintenance must not clear the
production output folder or erase the history used to avoid repeating work.
