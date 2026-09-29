# Getting more useful conversions through

These changes remove avoidable failures without lowering quality, size, timing,
or track-preservation requirements. They are not a promise that every source can
be made smaller.

- **Read more than the first packet.** Missing Dolby Vision headers are inspected
  across bounded portions of the video, even when color tags are missing. A short
  unchanged copy recovers profile signaling. Missing color fields can be filled
  from consistent decoded-frame evidence; existing declarations are not overwritten.
- **Check more of long videos.** Sources at least 30 minutes long use five spaced
  sections instead of three. This increases screening cost but can avoid wasting
  a full encode on an unsuitable candidate. It is temporal coverage, not a claim
  of automatic scene recognition or whole-film perceptual proof.
- **Keep heavy checks from piling up.** App workers share one heavy-validation
  slot for decoded-frame readers and common HDR/VMAF processing. Encoding can
  still run in parallel under the existing resource governor. The OS releases
  the slot after process death. Waiting appears as a resource wait, not progress.
  This reduces concurrent peaks; it is not a hard memory cap or an OOM guarantee.
- **Recognize changed inputs.** New records retain filesystem identity and change
  time as well as size and modification time. Retry mode no longer protects a
  successful result for a different version of the source. Existing active work
  remains protected. The sampling-policy version invalidates old automatic keep
  decisions; confirmed replacements and explicit keeps are not indiscriminately
  requeued. Legacy records keep their existing signature checks.
- **Track generated outputs.** Shared command outputs are recorded independently
  of their extensions. Cleanup retains deliverables and small evidence records,
  rejects changed/unsafe artifacts, and recognizes additional audio intermediates.
  At startup, known terminal jobs are reconciled. Abruptly interrupted active
  work and publication recovery records remain protected for review.
- **Make replacement recovery clearer.** A durable `published-verified` state
  is saved before removing original links. Directory changes are synchronized
  after finalization. Failure-injection tests cover each journal stage. Recovery
  backups are not automatically deleted or guessed to be redundant.
- **Separate execution from outcome.** A completed development command is not a
  successful conversion or reclaimed disk space. Sample-only successes are no
  longer counted as size/quality rejections. Only confirmed replacements count
  toward library savings.

## Audio is still an explicit decision

A source audio decoding error is not an encoder failure. The default preserves
every track and stops rather than dropping a failing TrueHD/Atmos track. Using
an existing compatibility track instead would change the audio deliverable and
requires a separate, explicit decision and validation. No such change is enabled
by these reliability fixes.

## Artwork and cut-scene metadata

HDR finalization now records the attachment paths actually created by extraction,
instead of guessing a JPEG or PNG extension. The attachment contents are still
checked against the source.

For the hardware Dolby Vision sample route, metadata is selected using each
decoded picture's original packet position and presentation timestamp. This
avoids assigning a cut scene's RPUs to different pictures when raw HEVC ordering
is inferred differently. Payload bytes are not edited. Missing, duplicate, or
ambiguous mappings stop the test; per-frame metadata equality, timing, quality,
and savings checks still apply. This change is not blanket qualification of
full-file or layered Dolby Vision routes. Packet-payload dumps are temporary work
files, not reports to retain indefinitely.

A reproduced 240-frame mismatch passed exact decoded metadata, RPU, timing,
copied-track, decode, and quality checks after this mapping change. Qualification
reused the identical encoded picture bytes after checking source-bitstream and
encoder-setting identity. That candidate was larger than its reference, so it
was not accepted as a space-saving conversion. Broader settings trials remain a
separate task. The follow-up Linux regression run passed 913 tests with five
skips, with its test subprocess restricted to four CPUs to avoid unbounded
fixture thread allocation alongside research work.

## Qualification

Linux regression tests cover history identity, cleanup manifests and restart
handling, publication interruption, and cross-process validation locking,
including release after process death. A generated NVIDIA DV fixture completed
full encoding and validation with the shared validation slot enabled. Synthetic
results are not a projection of savings on a real library. Production deployment
and a real-library retry are separate steps.

The final Linux regression run executed 912 tests: 907 passed and five were
skipped. Generated SDR and Dolby Vision full-encode checks passed on NVIDIA.
The SDR check also verified cleanup of eight temporary artifacts while retaining
its deliverable. These tiny fixtures used a zero minimum-savings threshold for
qualification only; production savings and quality requirements were unchanged.
