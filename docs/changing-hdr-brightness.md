# Keeping changing HDR brightness information

Some sources change their content-light values during playback. An encoder can
keep the first values throughout the copy, even when HDR10+ scene information
survives. We must preserve both; ignoring the mismatch is not a fix.

The shared HEVC finalizer restores content-light information for each frame when
the source contains changing values. It uses decoded frame order and packet
positions to handle B-frame reordering. It does not change picture slices,
mastering-display information, or HDR10+ messages. It writes only a new working
copy and records a picture-payload hash check.

The normal whole-frame HDR, timing, decode, size and quality checks still apply.
A successful metadata repair alone never authorizes replacement. Missing or
ambiguous frame evidence remains an error rather than a guess.

The regression suite covers reordered frames, malformed evidence, source
protection and unchanged picture data. Real-media qualification is tracked on
the development dashboard; this is not a claim of full-file qualification.

The content-light payload uses the two unsigned 16-bit fields documented in
[FFmpeg's SEI implementation](https://github.com/FFmpeg/FFmpeg/blob/master/libavcodec/cbs_sei_syntax_template.c).
