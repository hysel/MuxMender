#!/bin/sh
# One fixed, inspected SDR source. Not a general HDR/DV conversion workflow.
set -eu
umask 077
source='/media/TV/Series/Season 1/Example.Series.S01E01-03.Episode.Part1-3.EXTENDED.1080p.BluRay.EAC3.AVC-PiR8.mkv'
test -r "$source"
run=$(mktemp -d /output/ExampleSeries-NVIDIA-XXXXXXXX)
echo "Results: $run"
trap 'echo "Interrupted/failed: inspect logs in $run"' 1 2 15
stat "$source" > "$run/source-before.txt"
ffmpeg -version > "$run/ffmpeg.txt"
ffprobe -v error -show_streams -show_format -of json "$source" > "$run/source.json"
profile=$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height,pix_fmt,color_transfer -of csv=p=0 "$source")
test "$profile" = 'h264,1920,1080,yuv420p,bt709' || { echo "Unexpected source profile: $profile"; exit 1; }
echo 'Creating approximately 30-second stream-copy reference near 10:00.'
echo reference > "$run/stage.txt"
timeout -k 5 180 ffmpeg -hide_banner -nostdin -n -ss 600 -i "$source" -t 30 -map 0 -c copy -map_chapters -1 -avoid_negative_ts make_zero -metadata title='Example Series - NVIDIA ORIGINAL reference' "$run/Original.mkv" > "$run/reference.log" 2>&1
ffprobe -v error -show_streams -show_format -of json "$run/Original.mkv" > "$run/reference.json"
for codec in hevc av1; do
  echo "$codec" > "$run/stage.txt"
  echo "Encoding $codec with NVENC, preset p5, VBR CQ 23; audio/subtitles copied."
  start=$(date +%s)
  timeout -k 5 600 ffmpeg -hide_banner -nostdin -n -i "$run/Original.mkv" -map 0 -map_metadata 0 -map_chapters -1 -c copy -c:v:0 "${codec}_nvenc" -preset p5 -tune hq -rc vbr -cq 23 -b:v 0 -pix_fmt yuv420p -fps_mode:v:0 passthrough -color_range tv -colorspace bt709 -color_primaries bt709 -color_trc bt709 -metadata title="Example Series - NVIDIA $codec CQ23" -progress "$run/$codec-progress.txt" "$run/$codec.mkv" > "$run/$codec.log" 2>&1
  end=$(date +%s)
  echo "$codec encode_seconds=$((end-start))" | tee -a "$run/timings.txt"
done
echo validating > "$run/stage.txt"
for name in Original hevc av1; do
  echo "Decode check: $name"
  timeout -k 5 180 ffmpeg -hide_banner -nostdin -v error -xerror -i "$run/$name.mkv" -map 0:v -map '0:a?' -f null - > "$run/$name-decode.log" 2>&1
  ffprobe -v error -count_frames -show_streams -show_format -of json "$run/$name.mkv" > "$run/$name-probe.json"
  # Packet hashes permit independent verification of copied audio/subtitles.
  ffprobe -v error -select_streams a -show_packets -show_data_hash sha256 -show_entries packet=stream_index,data_hash -of json "$run/$name.mkv" > "$run/$name-audio-hashes.json"
  ffprobe -v error -select_streams s -show_packets -show_data_hash sha256 -show_entries packet=stream_index,data_hash -of json "$run/$name.mkv" > "$run/$name-subtitle-hashes.json"
  stat -c '%n %s' "$run/$name.mkv" >> "$run/sizes.txt"
done
stat "$source" > "$run/source-after.txt"
echo completed-pending-metadata-and-playback-review > "$run/stage.txt"
echo "Encoding and full A/V decode checks completed: $run"
cat "$run/sizes.txt"
echo 'CQ23 is a starting point, not an equal-quality guarantee between codecs.'
echo 'No source files were changed. Review metadata and playback before any batch.'
