# Verified Dolby Vision replacement

Fresh automatic NVIDIA Profile 5 and Profile 7 results can now qualify for the
existing journaled publisher. This removes the blanket copy-only restriction;
it does not make the encoder replace files or override the user's copy/replace
selection.

Qualification requires full-source and output identities, complete frame and
track evidence, requested quality floors, and the final savings check. Layered
sources additionally require enhancement/RPU preservation and both native and
fallback quality views. The publisher independently rechecks hashes, destination
safety and exact savings before its existing staging/verification transaction.

Explicit experimental outputs remain copy-only. Old result records are not
rewritten or automatically promoted. Missing full-output hashes and incomplete
evidence still fail. Other hardware qualification remains deferred for Phase 1.

Remote tests exercised fresh automatic Profile 5 and MEL conversions followed
by real publication transactions on disposable generated copies. Both completed
replacement, output-hash verification and cleanup, with reference fixtures
unchanged. Existing image P5, MEL and FEL evidence passed the new qualification
check against actual output hashes. These checks did not alter library media.
The regression suite passed 848 tests, including rejected incomplete evidence
and explicit experimental isolation.

At this research checkpoint the change was not deployed and was absent from the
earlier qualification image. The current v41 tree includes this qualification
path; see [supported use cases](SUPPORTED-USE-CASES.md). This note is not evidence
that an arbitrary source is approved or that a local change has been deployed.
