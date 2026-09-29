# When input checks stop a conversion

An input problem is different from a video that would not shrink enough.
Both keep the original, but only the input problem belongs in **Needs attention**.

## Missing Dolby Vision information

Some HEVC files contain Dolby Vision data without declaring its profile in the
container header. The shared reader now checks the decoded data and, when needed,
repackages a short unchanged video copy to recover the declaration. It never
edits the source or overwrites an existing declaration. Temporary copies are
removed after inspection.

This identifies which conversion path to try. It is not a validation shortcut:
RPU content, frame order, timing, tracks, quality and size checks still apply.

An isolated 30-second copy exercised the recovered Profile 8.1 NVIDIA route.
All three tested sections passed metadata/track preservation and the unchanged
quality checks. The tested encoding was larger, so it was correctly rejected for
size. This qualifies the routing fix, not the full source or a savings claim.

## Source audio cannot be decoded

The app checks source audio before spending time encoding video. A decoder error
can reflect the source bitstream or a decoder limitation; it is not proof that
the GPU encoder failed.

In the current TrueHD investigation, two inputs failed with both the installed
and newer FFmpeg decoder, using one and two decoder threads. Copying the audio
without re-encoding into raw TrueHD and Matroska audio did not resolve the error.
A third input reached the same audio error after its missing Dolby Vision header
was recovered. These inputs are **not fixed or approved for replacement**.

The app does not silently remove the affected track, substitute a different audio
track, or conceal errors. The next step is a known-good source track or a separately
tested decoder/repair approach. Retrying unchanged settings alone is unlikely to help.
