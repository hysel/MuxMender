# Withdrawn workarounds — historical investigation record

Both acceptance relaxations below are now removed. The original 2 ms packet
timing check and 20-second reference bound apply. The evaluation policy ID is
restored to source-driven-hdr-quality-search-1. Neither workaround was deployed.
The following describes the withdrawn experiment, not current behavior.

Not deployed; no new release created.

Timing case A's reference-1 duration is 20.019 seconds. The old 10-second
sampling rule stopped at exactly 20 seconds. A proposed frame-based allowance
was withdrawn after user review: keyframe preroll has not been proven to explain
the doubled sample duration. The original 20-second bound remains; 20.019 seconds
still fails. Investigate actual source keyframes and sample start/end alignment
before changing this policy. No allowance was deployed.

Timing case C's first sample retained all 1,080 DTS-HD MA packet hashes.
One packet's PTS and DTS changed by -3 ms. Audio alone now permits up to 5 ms,
limited to half the shorter packet duration, while the offset spread across
the entire track may not exceed 5 ms. New timestamp reversals fail. Packet
payload/count and duration checks remain unchanged, as do the 2 ms subtitle
and video timing checks. Unknown packet durations retain the strict 2 ms rule.
This is a bounded tolerance policy, not proof that the muxer caused rounding.
Each copied track gets an audit JSON with the measured timing difference.

Replayed actual retained evidence locally: all 1,080 Timing case C audio packets
passed the proposed audio policy. Timing case A's generated reference remains rejected.
Full video quality/preservation/decode checks still need to finish on retry;
these fixes do not authorize a replacement on their own.

Evaluation policy bumped to source-driven-hdr-quality-search-2 so old negative
decisions do not silently prevent re-evaluation under the updated policy.
Tests cover the observed patterns plus packet changes/loss, drift, excessive
offsets, order reversal, invalid durations and excessive sampling windows.
