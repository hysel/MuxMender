// Diagnostic only: software decode, D3D11 color conversion, lossless FFV1.
// Output is exclusively created; existing files are never opened for writing.
#include <windows.h>
#include <libplacebo/d3d11.h>
#include <libplacebo/renderer.h>
#define PL_LIBAV_IMPLEMENTATION 0
#include <libplacebo/utils/libav.h>
extern "C" {
#include <libswscale/swscale.h>
#include <libavutil/opt.h>
}
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

static void check(int result, const char* what) {
    if (result < 0) {
        char message[AV_ERROR_MAX_STRING_SIZE];
        av_strerror(result, message, sizeof(message));
        throw std::runtime_error(std::string(what) + ": " + message);
    }
}
static void require(bool ok, const char* what) { if (!ok) throw std::runtime_error(what); }
static std::string utf8(const std::wstring& text) {
    int size = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, text.data(), int(text.size()), nullptr, 0, nullptr, nullptr);
    require(size > 0, "Invalid path");
    std::string result(size, '\0');
    require(WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, text.data(), int(text.size()), result.data(), size, nullptr, nullptr) == size, "Invalid path");
    return result;
}
struct State {
    AVFormatContext *input = nullptr, *output = nullptr;
    AVCodecContext *decoder = nullptr, *encoder = nullptr;
    AVPacket *packet = av_packet_alloc(), *encoded = av_packet_alloc();
    AVFrame *frame = av_frame_alloc(), *converted = av_frame_alloc();
    AVIOContext* io = nullptr;
    HANDLE file = INVALID_HANDLE_VALUE;
    SwsContext* scale = nullptr;
    pl_log log = nullptr;
    pl_d3d11 device = nullptr;
    pl_renderer renderer = nullptr;
    pl_tex textures[4]{}, target = nullptr;
    ~State() {
        if (device) {
            pl_tex_destroy(device->gpu, &target);
            for (auto& texture : textures) pl_tex_destroy(device->gpu, &texture);
            pl_renderer_destroy(&renderer);
            pl_d3d11_destroy(&device);
        }
        pl_log_destroy(&log);
        sws_freeContext(scale);
        av_frame_free(&frame); av_frame_free(&converted);
        av_packet_free(&packet); av_packet_free(&encoded);
        avcodec_free_context(&decoder); avcodec_free_context(&encoder);
        avformat_close_input(&input);
        if (output) { output->pb = nullptr; avformat_free_context(output); }
        if (io) { av_freep(&io->buffer); avio_context_free(&io); }
        if (file != INVALID_HANDLE_VALUE) CloseHandle(file);
    }
};
static int write_bytes(void* opaque, const uint8_t* bytes, int count) {
    DWORD written = 0;
    auto* state = static_cast<State*>(opaque);
    if (!WriteFile(state->file, bytes, count, &written, nullptr) || written != DWORD(count)) return AVERROR(EIO);
    return count;
}
static int64_t seek_bytes(void* opaque, int64_t offset, int whence) {
    auto* state = static_cast<State*>(opaque);
    LARGE_INTEGER position{}, result{};
    if (whence == AVSEEK_SIZE) return GetFileSizeEx(state->file, &result) ? result.QuadPart : AVERROR(EIO);
    position.QuadPart = offset;
    int mode = whence & ~AVSEEK_FORCE;
    if (mode < SEEK_SET || mode > SEEK_END) return AVERROR(EINVAL);
    return SetFilePointerEx(state->file, position, &result, mode) ? result.QuadPart : AVERROR(EIO);
}
static double number(const wchar_t* value) {
    std::wstring text(value);
    size_t used = 0;
    double result = std::stod(text, &used);
    require(used == text.size() && std::isfinite(result), "Invalid numeric argument");
    return result;
}
int wmain(int argc, wchar_t** argv) {
    try {
        std::wstring inputPath, outputPath;
        double start = 0, seconds = 3;
        bool consent = false, hdr = false, dryRun = false, machineProgress = false, streamOutput = false, fullFile = false, rangeGiven = false;
        for (int i = 1; i < argc; ++i) {
            std::wstring arg = argv[i];
            if (arg == L"--sdr-preview") consent = true;
            else if (arg == L"--hdr-preview") hdr = true;
            else if (arg == L"--progress-machine") machineProgress = true;
            else if (arg == L"--dry-run") dryRun = true;
            else if (arg == L"--stream-output") streamOutput = true;
            else if (arg == L"--full-file") fullFile = true;
            else if (arg == L"--help") {
                std::cout << "--input PATH --output NEW.mkv (--sdr-preview | --hdr-preview) [--start SECONDS] [--seconds 1..10] [--dry-run]\n"
                             "Diagnostic DV profile 5 to SDR BT.709 preview; original dimensions; video only, no audio/subtitles.\n"
                             "--hdr-preview instead outputs BT.2020/PQ HDR without Dolby Vision dynamic metadata.\n"
                             "No AMF encoding. Existing outputs are refused. Failed partial outputs are retained.\n";
                std::cout << "--stream-output: HDR only, binary Matroska to a pipe on stdout; logs on stderr; no --output; seconds 1..60.\n";
                std::cout << "--full-file: explicit full-file streaming to EOF; requires --stream-output and --hdr-preview; no --start or --seconds.\n";
                return 0;
            } else {
                require(i + 1 < argc, "Missing argument value");
                if (arg == L"--input") inputPath = argv[++i];
                else if (arg == L"--output") outputPath = argv[++i];
                else if (arg == L"--start") { start = number(argv[++i]); rangeGiven = true; }
                else if (arg == L"--seconds") { seconds = number(argv[++i]); rangeGiven = true; }
                else throw std::runtime_error("Unknown option");
            }
        }
        require(!inputPath.empty() && (streamOutput ? outputPath.empty() : !outputPath.empty()), "Input and exactly one output mode are required");
        require(consent != hdr, "Explicit --sdr-preview or --hdr-preview is required, but not both");
        require(!fullFile || (streamOutput && hdr && !rangeGiven), "Full-file mode requires HDR streaming without range arguments");
        require(start >= 0 && seconds >= 1 && seconds <= (streamOutput ? 60 : 10), "Start/duration outside bounded output mode limits");
        if (streamOutput) {
            require(hdr, "Streaming requires explicit HDR preview consent");
            require(GetFileType(GetStdHandle(STD_OUTPUT_HANDLE)) == FILE_TYPE_PIPE, "Streaming stdout must be a pipe, not a file or terminal");
            std::cout.rdbuf(std::cerr.rdbuf()); // Never mix logs with binary stdout.
        } else {
            require(GetFileAttributesW(outputPath.c_str()) == INVALID_FILE_ATTRIBUTES, "Output already exists; refusing to overwrite");
        }
        State s;
        require(s.packet && s.encoded && s.frame && s.converted, "Allocation failed");
        check(avformat_open_input(&s.input, utf8(inputPath).c_str(), nullptr, nullptr), "Open input read-only");
        check(avformat_find_stream_info(s.input, nullptr), "Read stream information");
        const AVCodec* codec = nullptr;
        int video = av_find_best_stream(s.input, AVMEDIA_TYPE_VIDEO, -1, -1, &codec, 0);
        check(video, "Find video");
        AVStream* stream = s.input->streams[video];
        auto* config = av_packet_side_data_get(stream->codecpar->coded_side_data, stream->codecpar->nb_coded_side_data, AV_PKT_DATA_DOVI_CONF);
        require(config && config->size >= sizeof(AVDOVIDecoderConfigurationRecord), "Missing Dolby Vision configuration");
        auto* dv = reinterpret_cast<AVDOVIDecoderConfigurationRecord*>(config->data);
        require(dv->dv_profile == 5 && dv->rpu_present_flag && !dv->el_present_flag, "Only single-layer Dolby Vision profile 5 is supported by this diagnostic");
        require(stream->codecpar->width > 0 && stream->codecpar->height > 0, "Invalid dimensions");
        if (fullFile) {
            require(s.input->duration > 0, "Full-file mode requires a known positive duration");
            seconds = double(s.input->duration) / AV_TIME_BASE;
            require(std::isfinite(seconds) && seconds <= 86400, "Full-file duration exceeds supported 24-hour bound");
        }
        const char* outputColor = hdr ? "HDR BT.2020/PQ (not Dolby Vision)" : "SDR BT.709";
        std::cout << "Plan: DV profile 5 -> " << outputColor << ", " << stream->codecpar->width << 'x' << stream->codecpar->height
                  << ", " << seconds << " seconds, software decode + D3D11 rendering + lossless FFV1. Video only.\n" << std::flush;
        if (dryRun) { std::cout << "Dry run: no GPU initialization or output creation.\n"; return 0; }
        s.decoder = avcodec_alloc_context3(codec);
        require(s.decoder, "Decoder allocation failed");
        check(avcodec_parameters_to_context(s.decoder, stream->codecpar), "Configure decoder");
        s.decoder->thread_count = 2;
        check(avcodec_open2(s.decoder, codec, nullptr), "Open decoder");
        int64_t origin = stream->start_time == AV_NOPTS_VALUE ? 0 : stream->start_time;
        int64_t first = origin + int64_t(start / av_q2d(stream->time_base));
        check(av_seek_frame(s.input, video, first, AVSEEK_FLAG_BACKWARD), "Seek input");
        avcodec_flush_buffers(s.decoder);
        pl_log_params logs{};
        logs.log_cb = [](void*, pl_log_level, const char* message) { std::cerr << message << '\n'; };
        logs.log_level = PL_LOG_WARN;
        s.log = pl_log_create(PL_API_VER, &logs);
        pl_d3d11_params deviceParams{}; deviceParams.min_feature_level = D3D_FEATURE_LEVEL_11_0;
        deviceParams.allow_software = false;
        s.device = pl_d3d11_create(s.log, &deviceParams);
        require(s.device, "D3D11 initialization failed");
        s.renderer = pl_renderer_create(s.log, s.device->gpu);
        require(s.renderer, "Renderer creation failed");
        int count = 0, width = 0, height = 0;
        int64_t basePts = AV_NOPTS_VALUE, lastPts = AV_NOPTS_VALUE;
        bool done = false;
        std::vector<uint16_t> pixels;
        auto drainEncoder = [&]() {
            while (true) {
                int result = avcodec_receive_packet(s.encoder, s.encoded);
                if (result == AVERROR(EAGAIN) || result == AVERROR_EOF) break;
                check(result, "Encode preview");
                av_packet_rescale_ts(s.encoded, s.encoder->time_base, s.output->streams[0]->time_base);
                s.encoded->stream_index = 0;
                check(av_interleaved_write_frame(s.output, s.encoded), "Write preview packet");
                av_packet_unref(s.encoded);
            }
        };
        auto process = [&]() {
            int64_t pts = s.frame->best_effort_timestamp;
            require(pts != AV_NOPTS_VALUE, "Missing frame timestamp");
            if (pts < first) return;
            if (!fullFile && av_q2d(stream->time_base) * (pts - first) >= seconds) { done = true; return; }
            require(lastPts == AV_NOPTS_VALUE || pts > lastPts, "Non-monotonic frame timestamps");
            require(av_frame_get_side_data(s.frame, AV_FRAME_DATA_DOVI_METADATA), "Frame is missing parsed Dolby Vision metadata; refusing incorrect colors");
            if (count == 0) {
                width = s.frame->width; height = s.frame->height; basePts = pts;
                require(width == stream->codecpar->width && height == stream->codecpar->height, "Unexpected dimensions");
                pl_tex_params texture{}; texture.w = width; texture.h = height;
                texture.format = pl_find_named_fmt(s.device->gpu, "rgba16");
                require(texture.format, "16-bit RGB render target unavailable");
                texture.renderable = true; texture.host_readable = true;
                s.target = pl_tex_create(s.device->gpu, &texture);
                require(s.target, "Render target allocation failed");
                pixels.resize(size_t(width) * height * 4);
                const AVCodec* encoder = avcodec_find_encoder(AV_CODEC_ID_FFV1);
                require(encoder, "FFV1 encoder unavailable");
                s.encoder = avcodec_alloc_context3(encoder);
                require(s.encoder, "Encoder allocation failed");
                s.encoder->width = width; s.encoder->height = height;
                s.encoder->pix_fmt = AV_PIX_FMT_YUV444P10LE;
                s.encoder->time_base = stream->time_base;
                s.encoder->framerate = av_guess_frame_rate(s.input, stream, s.frame);
                s.encoder->sample_aspect_ratio = s.frame->sample_aspect_ratio;
                s.encoder->color_primaries = hdr ? AVCOL_PRI_BT2020 : AVCOL_PRI_BT709;
                s.encoder->color_trc = hdr ? AVCOL_TRC_SMPTE2084 : AVCOL_TRC_BT709;
                s.encoder->colorspace = hdr ? AVCOL_SPC_BT2020_NCL : AVCOL_SPC_BT709;
                s.encoder->color_range = AVCOL_RANGE_MPEG;
                s.encoder->thread_count = 2;
                check(avformat_alloc_output_context2(&s.output, nullptr, "matroska", nullptr), "Allocate Matroska muxer");
                if (s.output->oformat->flags & AVFMT_GLOBALHEADER) s.encoder->flags |= AV_CODEC_FLAG_GLOBAL_HEADER;
                check(avcodec_open2(s.encoder, encoder, nullptr), "Open FFV1 encoder");
                AVStream* outputStream = avformat_new_stream(s.output, nullptr);
                require(outputStream, "Output stream allocation failed");
                check(avcodec_parameters_from_context(outputStream->codecpar, s.encoder), "Set output metadata");
                outputStream->time_base = s.encoder->time_base;
                outputStream->avg_frame_rate = s.encoder->framerate;
                s.converted->format = s.encoder->pix_fmt; s.converted->width = width; s.converted->height = height;
                s.converted->color_primaries = s.encoder->color_primaries;
                s.converted->color_trc = s.encoder->color_trc;
                s.converted->colorspace = s.encoder->colorspace; s.converted->color_range = AVCOL_RANGE_MPEG;
                check(av_frame_get_buffer(s.converted, 32), "Allocate output frame");
                s.scale = sws_getContext(width, height, AV_PIX_FMT_RGBA64LE, width, height, s.encoder->pix_fmt, SWS_BICUBIC, nullptr, nullptr, nullptr);
                require(s.scale, "Pixel converter creation failed");
                int matrix = hdr ? SWS_CS_BT2020 : SWS_CS_ITU709;
                check(sws_setColorspaceDetails(s.scale, sws_getCoefficients(matrix), 1, sws_getCoefficients(matrix), 0, 0, 1 << 16, 1 << 16), "Set RGB/YUV matrix");
                s.file = streamOutput ? GetStdHandle(STD_OUTPUT_HANDLE) : CreateFileW(outputPath.c_str(), GENERIC_WRITE, FILE_SHARE_READ, nullptr, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr);
                require(s.file != INVALID_HANDLE_VALUE, "Cannot exclusively create output (existing files are never overwritten)");
                auto* buffer = static_cast<unsigned char*>(av_malloc(65536));
                require(buffer, "Output buffer allocation failed");
                s.io = avio_alloc_context(buffer, 65536, 1, &s, nullptr, write_bytes, streamOutput ? nullptr : seek_bytes);
                if (!s.io) { av_free(buffer); throw std::runtime_error("Output I/O allocation failed"); }
                s.output->pb = s.io; s.output->flags |= AVFMT_FLAG_CUSTOM_IO;
                if (streamOutput) {
                    s.io->seekable = 0;
                    check(av_opt_set_int(s.output->priv_data, "live", 1, 0), "Set streaming Matroska mode");
                    check(av_opt_set_int(s.output->priv_data, "cluster_time_limit", 1000, 0), "Bound streaming cluster duration");
                }
                check(avformat_write_header(s.output, nullptr), "Write Matroska header");
            }
            require(s.frame->width == width && s.frame->height == height, "Mid-stream dimension change is unsupported");
            pl_frame mapped{};
            pl_avframe_params mapping{}; mapping.frame = s.frame; mapping.tex = s.textures; mapping.map_dovi = true;
            require(pl_map_avframe_ex(s.device->gpu, &mapped, &mapping), "Map decoded frame");
            pl_frame destination{}; destination.num_planes = 1; destination.planes[0].texture = s.target;
            destination.planes[0].components = 3;
            for (int c = 0; c < 3; ++c) destination.planes[0].component_mapping[c] = c;
            destination.repr = pl_color_repr_rgb;
            // Keep the source's reconstructed PQ color volume for HDR. Do not
            // tone-map to a generic lower peak or invent mastering primaries.
            destination.color = hdr ? mapped.color : pl_color_space_bt709;
            bool rendered = mapped.repr.dovi && pl_render_image(s.renderer, &mapped, &destination, &pl_render_default_params);
            pl_unmap_avframe(s.device->gpu, &mapped);
            require(rendered, "Dolby Vision rendering failed");
            pl_tex_transfer_params transfer{}; transfer.tex = s.target; transfer.ptr = pixels.data();
            require(pl_tex_download(s.device->gpu, &transfer), "Download corrected frame");
            check(av_frame_make_writable(s.converted), "Make encoder frame writable");
            const uint8_t* planes[] = { reinterpret_cast<uint8_t*>(pixels.data()), nullptr, nullptr, nullptr };
            int strides[] = { width * 8, 0, 0, 0 };
            require(sws_scale(s.scale, planes, strides, 0, height, s.converted->data, s.converted->linesize) == height, "Pixel conversion incomplete");
            s.converted->pts = pts - basePts;
            check(avcodec_send_frame(s.encoder, s.converted), "Send encoder frame");
            drainEncoder();
            lastPts = pts; ++count;
            int percent = std::min(99, int(100 * av_q2d(stream->time_base) * (pts - first) / seconds));
            std::cout << '\r' << '[' << std::string(percent / 5, '=') << std::string(20 - percent / 5, ' ') << "] " << percent << "% " << count << " frames" << std::flush;
            if (machineProgress) std::cout << "\nMUXMENDER_PROGRESS=" << percent << '\n' << std::flush;
        };
        auto drainDecoder = [&]() {
            while (!done) {
                int result = avcodec_receive_frame(s.decoder, s.frame);
                if (result == AVERROR(EAGAIN) || result == AVERROR_EOF) break;
                check(result, "Decode frame"); process(); av_frame_unref(s.frame);
            }
        };
        while (!done) {
            int result = av_read_frame(s.input, s.packet);
            if (result == AVERROR_EOF) { check(avcodec_send_packet(s.decoder, nullptr), "Flush decoder"); drainDecoder(); break; }
            check(result, "Read input packet");
            if (s.packet->stream_index == video) { check(avcodec_send_packet(s.decoder, s.packet), "Submit video packet"); drainDecoder(); }
            av_packet_unref(s.packet);
        }
        require(count > 0, "No frames in requested interval");
        check(avcodec_send_frame(s.encoder, nullptr), "Flush encoder"); drainEncoder();
        check(av_write_trailer(s.output), "Finalize preview"); avio_flush(s.io);
        check(s.io->error, "Flush output");
        if (!streamOutput) require(FlushFileBuffers(s.file), "Flush output to disk");
        if (machineProgress) std::cout << "\nMUXMENDER_PROGRESS=100\n" << std::flush;
        std::cout << "\r[====================] 100% " << count << " frames\nMUXMENDER_DV_PREVIEW={\"ok\":true,\"frames\":" << count
                  << ",\"width\":" << width << ",\"height\":" << height << ",\"output_color\":\"" << outputColor << "\",\"audio_included\":false}\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "\nPreview failed: " << error.what() << "\nOriginals are untouched. Any newly created partial output is retained.\n";
        return 1;
    }
}
