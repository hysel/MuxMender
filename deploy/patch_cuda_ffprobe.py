"""Build-only patch for a pinned, isolated FFprobe CUDA metadata experiment.

Not a production reader. Retains the upstream JSON/side-data serializer and
decodes with the native HEVC parser plus NVDEC; never guesses HDR metadata.
"""
import argparse
from pathlib import Path


def transform(source, allow_av1=False):
    def change(old, new):
        nonlocal source
        if source.count(old)!=1: raise ValueError('Pinned FFprobe patch anchor changed')
        source=source.replace(old,new)
    change('#include "libavutil/pixdesc.h"', '#include "libavutil/pixdesc.h"\n#include "libavutil/hwcontext.h"')
    anchor='static void show_frame('
    if source.count(anchor)!=1: raise ValueError('FFprobe frame serializer anchor changed')
    helper='''/* Research-only: CUDA must not silently fall back to software. */
static enum AVPixelFormat muxmender_cuda_format(AVCodecContext *ctx,
                                               const enum AVPixelFormat *formats)
{
    while (*formats != AV_PIX_FMT_NONE) {
        if (*formats == AV_PIX_FMT_CUDA) return *formats;
        formats++;
    }
    av_log(ctx, AV_LOG_ERROR, "CUDA metadata decode unavailable; no software fallback\\n");
    return AV_PIX_FMT_NONE;
}

static int muxmender_cuda_requested(void)
{
    const char *value = getenv("MUXMENDER_RESEARCH_CUDA_READER");
    return value && !strcmp(value, "1");
}

'''
    source=source.replace(anchor,helper+anchor)
    change('            ist->dec_ctx->pkt_timebase = stream->time_base;', '''            ist->dec_ctx->pkt_timebase = stream->time_base;
            if (muxmender_cuda_requested() && stream->codecpar->codec_type == AVMEDIA_TYPE_VIDEO &&
                (!stream_specifier || avformat_match_stream_specifier(fmt_ctx, stream, stream_specifier) > 0)) {
                if (stream->codecpar->codec_id != AV_CODEC_ID_HEVC) {
                    av_log(NULL, AV_LOG_ERROR, "CUDA research reader currently qualifies HEVC only\\n");
                    return AVERROR(ENOSYS);
                }
                err = av_hwdevice_ctx_create(&ist->dec_ctx->hw_device_ctx,
                                            AV_HWDEVICE_TYPE_CUDA, NULL, NULL, 0);
                if (err < 0) return err;
                ist->dec_ctx->get_format = muxmender_cuda_format;
            }''')
    change('''                ret = avcodec_receive_frame(dec_ctx, frame);
                if (ret >= 0) {
                    got_frame = 1;''', '''                ret = avcodec_receive_frame(dec_ctx, frame);
                if (ret >= 0) {
                    if (muxmender_cuda_requested() && frame->format == AV_PIX_FMT_CUDA &&
                        (frame->decode_error_flags || (frame->flags & AV_FRAME_FLAG_CORRUPT))) {
                        av_log(dec_ctx, AV_LOG_ERROR, "CUDA reported corrupt decoded frame\\n");
                        av_frame_unref(frame);
                        return AVERROR_INVALIDDATA;
                    }
                    got_frame = 1;''')
    change('''            else
                show_frame(tfc, frame, ifile->streams[pkt->stream_index].st, fmt_ctx);''', '''            else {
                const int original_format = frame->format;
                if (original_format == AV_PIX_FMT_CUDA) {
                    AVHWFramesContext *hw;
                    if (!frame->hw_frames_ctx) return AVERROR_INVALIDDATA;
                    hw = (AVHWFramesContext*)frame->hw_frames_ctx->data;
                    /* JSON describes decoded chroma/depth, not GPU storage layout.
                     * No download, scaling or changes to frame properties occur.
                     * Unsupported layouts fail rather than inventing a format. */
                    switch (hw->sw_format) {
                    case AV_PIX_FMT_NV12: frame->format = AV_PIX_FMT_YUV420P; break;
                    case AV_PIX_FMT_P010LE: frame->format = AV_PIX_FMT_YUV420P10LE; break;
                    default:
                        av_log(NULL, AV_LOG_ERROR, "Unqualified CUDA metadata storage layout\\n");
                        return AVERROR(ENOSYS);
                    }
                }
                show_frame(tfc, frame, ifile->streams[pkt->stream_index].st, fmt_ctx);
                frame->format = original_format;
            }''')
    if allow_av1:
        source=source.replace('stream->codecpar->codec_id != AV_CODEC_ID_HEVC)',
            'stream->codecpar->codec_id != AV_CODEC_ID_HEVC && stream->codecpar->codec_id != AV_CODEC_ID_AV1)')
        source=source.replace('CUDA research reader currently qualifies HEVC only',
            'CUDA research reader tests HEVC and AV1 only')
    return source


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path)
    p.add_argument('--decoder',type=Path);p.add_argument('--nvdec',type=Path)
    p.add_argument('--av1',action='store_true',help='Experimental AV1; retain strict driver status checks')
    args=p.parse_args();args.source.write_text(transform(args.source.read_text(),args.av1))
    if args.decoder:args.decoder.write_text(transform_hevc_bounds(args.decoder.read_text()))
    if args.nvdec:args.nvdec.write_text(transform_nvdec_status(args.nvdec.read_text()))


def transform_hevc_bounds(source):
    """Keep upstream RBSP entry-point bounds checks on the hardware path too."""
    old='''    if (s->avctx->hwaccel)
        return FF_HW_CALL(s->avctx, decode_slice, nal->raw_data, nal->raw_size);'''
    new='''    if (s->avctx->hwaccel) {
        const char *research = getenv("MUXMENDER_RESEARCH_CUDA_READER");
        if (research && !strcmp(research, "1")) {
            int64_t offset = s->sh.data_offset;
            int i, j;
            /* Entry offsets include emulation-prevention bytes. Match the
             * software WPP accounting without decoding pixels on the CPU. */
            for (i = 0; i < s->sh.num_entry_point_offsets; i++) {
                int64_t end = offset + s->sh.entry_point_offset[i];
                for (j = 0; j < nal->skipped_bytes; j++) {
                    if (nal->skipped_bytes_pos[j] >= offset &&
                        nal->skipped_bytes_pos[j] < end) end--;
                }
                if (end < offset || end > nal->size) {
                    av_log(s->avctx, AV_LOG_ERROR,
                           "CUDA slice entry-point bounds are corrupted\\n");
                    return AVERROR_INVALIDDATA;
                }
                offset = end;
            }
        }
        return FF_HW_CALL(s->avctx, decode_slice, nal->raw_data, nal->raw_size);
    }'''
    if source.count(old)!=1:raise ValueError('Pinned HEVC bounds anchor changed')
    return source.replace(old,new)


def transform_nvdec_status(source):
    """Wait for actual completion and reject errors, including concealed ones."""
    include='#include "libavutil/error.h"'
    if source.count(include)!=1:raise ValueError('Pinned NVDEC include anchor changed')
    source=source.replace(include,include+'\n#include "libavutil/time.h"')
    old='''    ret = CHECK_CU(decoder->cvdl->cuvidDecodePicture(decoder->decoder, &ctx->pic_params));
    if (ret < 0)
        goto finish;

finish:'''
    new='''    ret = CHECK_CU(decoder->cvdl->cuvidDecodePicture(decoder->decoder, &ctx->pic_params));
    if (ret < 0)
        goto finish;

    {
        const char *research = getenv("MUXMENDER_RESEARCH_CUDA_READER");
        if (research && !strcmp(research, "1")) {
            CUVIDGETDECODESTATUS status = { 0 };
            int attempt;
            if (!decoder->cvdl->cuvidGetDecodeStatus) {
                ret = AVERROR(ENOSYS);
                goto finish;
            }
            /* A submitted frame is not proof of successful decoding. No
             * pixel transfer is needed for the driver's completion status. */
            for (attempt = 0; attempt < 5000; attempt++) {
                ret = CHECK_CU(decoder->cvdl->cuvidGetDecodeStatus(
                    decoder->decoder, pp->CurrPicIdx, &status));
                if (ret < 0) goto finish;
                if (status.decodeStatus != cuvidDecodeStatus_InProgress) break;
                av_usleep(1000);
            }
            if (status.decodeStatus != cuvidDecodeStatus_Success) {
                av_log(avctx, AV_LOG_ERROR,
                       "CUDA decoding not confirmed clean: status %d\\n",
                       status.decodeStatus);
                ret = AVERROR_INVALIDDATA;
            }
        }
    }

finish:'''
    if source.count(old)!=1:raise ValueError('Pinned NVDEC status anchor changed')
    return source.replace(old,new)


if __name__=='__main__':main()
