# Docker releases and hosting plan

The current release still uses a staged build package. A manual publishing
workflow and installation template are now prepared; no public image has been
announced. See [release operations](container-release-operations.md) for the
runner, review materials and remaining readiness requirements.

## Make installation a pull, not a build

Publish the app image to **GitHub Container Registry** under the proposed name
`ghcr.io/hysel/muxmender`. Users would select an exact released version in
TrueNAS rather than compiling FFmpeg on their own server. This hosts the image,
not anyone's dashboard, media or processing jobs.

Start with Linux amd64 and NVIDIA. Don't advertise ARM or other GPU families
until the complete image and shared workflow support them.

## Release flow

1. Merge reviewed source through the protected main branch.
2. Select a commit and a version. Build from that commit with checksum-verified
   dependency archives and the packaged, qualified reader—not private work folders.
3. Run ordinary checks in CI. Run hardware-dependent image checks on a controlled
   NVIDIA runner without exposing production media or accepting untrusted PR code.
4. Publish a release candidate image and record its digest. Keep it out of the
   stable channel until its image checks pass.
5. Promote the **same digest**, rather than rebuilding it, to the released version.
6. Publish a GitHub Release with user-facing changes, upgrade instructions,
   supported platform, digest and rollback instructions. Keep detailed research
   results separate from the user wiki.

Use immutable version tags and record image digests. A later correction gets a
new version; don't silently overwrite an existing release. A moving `stable`
tag may be convenient later, but exact versions should remain the documented
choice. The isolated clean-base candidate passed its image checks, but public
promotion still waits for complete release materials, security review and
installation/pull checks. A candidate-test pass is not a publication announcement.

## Repository work before the first public image

- Make release inputs reproducible from a clean checkout. Source archives and
  reader qualification currently need explicit packaging; a plain Docker build
  from the repository is not enough.
- Confirm redistribution requirements for FFmpeg's GPL-enabled build and every
  bundled runtime. Include license notices and the applicable corresponding
  source/build material with the release. This is a release requirement, not a
  claim that the review is complete.
- Add OCI source, revision, version and license labels; document dependency versions.
- Add a manual release workflow with narrowly scoped package-write permissions.
  Publish only from approved commits. Pin third-party actions to reviewed commits.
- Generate a software bill of materials and provenance; scan dependencies and
  review findings before promotion.
- Make the GHCR package public intentionally so users can pull without registry
  credentials. Verify an anonymous pull from a clean machine.
- Ship a small TrueNAS installation template alongside each release: folders,
  app user, host port and GPU assignment. No fixed pool paths or GPU UUIDs.
- Include the GPU-monitor integration and explain what access it needs. No
  privileged container or Docker socket just to browse or convert media.
- Validate updates with persistent history, queued jobs and interrupted work.
  Explain rollback limits if a future release changes saved-state formats.
- Keep the current release and a known-good rollback version. Remove old candidates
  only when unreferenced; never use registry housekeeping to delete user data.

## Wiki ownership

The user guide lives in `docs/wiki/` so it can be reviewed with the code. GitHub's
Wiki is a separate Git repository. Before publishing, initialize its Home page,
then synchronize these reviewed pages and adapt local `.md` links to wiki URLs.
Keep installation guidance matched to released images rather than promising that
every feature on main is already installed.

GitHub references: [Container Registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry),
[editing a wiki](https://docs.github.com/en/communities/documenting-your-project-with-wikis/adding-or-editing-wiki-pages).
