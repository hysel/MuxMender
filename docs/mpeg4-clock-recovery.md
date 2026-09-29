# More flexible source clock recovery

Development change after v39: MPEG-4 Visual recovery now checks the actual codec
and source identity instead of requiring an AVI filename. Extraction includes
container-held headers; group clock headers are parsed rather than rejected.

Generated AVI, MP4 and MKV fixtures with B pictures passed 50-frame clock
alignment on Linux. MP4/MKV tests deliberately removed the final timestamp from
the probe evidence and recovered the known value exactly. The generated AVI
already had an absent final decoded timestamp. No source file was modified.

Recovery remains limited to one absent final source timestamp. Every other
timestamp and picture type must agree with the coded clock, with the existing
one-microsecond serialization allowance. Invalid syntax, ambiguity and drift
still fail. This is not an FPS estimate or permission to change frame timing.

The group clock implementation follows FFmpeg's MPEG-4 decoder:
https://raw.githubusercontent.com/FFmpeg/FFmpeg/n8.0/libavcodec/mpeg4videodec.c

Not yet deployed. Unusual MPEG-4 object shapes and sprite clocks remain separate
parser work, not reasons to bypass timing verification.
