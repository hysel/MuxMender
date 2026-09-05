// Generated SDR pixels only: no media input, encoder, or output files.
#include <libplacebo/d3d11.h>
#include <libplacebo/renderer.h>
#include <algorithm>
#include <array>
#include <cstdlib>
#include <iostream>

int main() {
    pl_log_params logging{};
    logging.log_cb = [](void*, pl_log_level, const char* message) { std::cerr << message << '\n'; };
    logging.log_level = PL_LOG_INFO;
    pl_log log = pl_log_create(PL_API_VER, &logging);
    pl_d3d11_params device_params{};
    device_params.min_feature_level = D3D_FEATURE_LEVEL_11_0;
    device_params.allow_software = false;
    pl_d3d11 device = pl_d3d11_create(log, &device_params);
    if (!device) {
        std::cerr << "D3D11 initialization failed\n";
        pl_log_destroy(&log);
        return 2;
    }
    const pl_gpu gpu = device->gpu;
    pl_renderer renderer = pl_renderer_create(log, gpu);
    constexpr int width = 64, height = 64;
    std::array<unsigned char, width * height * 4> input{}, output{};
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            const int offset = (y * width + x) * 4;
            // Red, green, blue, and neutral gray bands, including alpha.
            for (int c = 0; c < 3; ++c)
                input[offset + c] = x / 16 == 3 ? 128 : (x / 16 == c ? 220 : 20);
            input[offset + 3] = 255;
        }
    }
    pl_tex_params tex_params{};
    tex_params.w = width;
    tex_params.h = height;
    tex_params.format = pl_find_named_fmt(gpu, "rgba8");
    if (!tex_params.format || !renderer) {
        std::cerr << "Required renderer/rgba8 format unavailable\n";
        pl_renderer_destroy(&renderer);
        pl_d3d11_destroy(&device);
        pl_log_destroy(&log);
        return 3;
    }
    tex_params.sampleable = true;
    tex_params.initial_data = input.data();
    pl_tex source = pl_tex_create(gpu, &tex_params);
    tex_params.initial_data = nullptr;
    tex_params.renderable = true;
    tex_params.host_readable = true;
    pl_tex target = pl_tex_create(gpu, &tex_params);
    pl_frame frame{};
    frame.num_planes = 1;
    frame.planes[0].texture = source;
    frame.planes[0].components = 4;
    for (int c = 0; c < 4; ++c) frame.planes[0].component_mapping[c] = c;
    frame.repr = pl_color_repr_rgb;
    frame.color = pl_color_space_srgb;
    pl_frame destination = frame;
    destination.planes[0].texture = target;
    std::cout << "Generated-color test [==========          ] 50%: rendering\n" << std::flush;
    bool ok = source && target && pl_render_image(renderer, &frame, &destination, &pl_render_default_params);
    pl_tex_transfer_params transfer{};
    transfer.tex = target;
    transfer.ptr = output.data();
    ok = ok && pl_tex_download(gpu, &transfer);
    int max_error = 0;
    if (ok) {
        for (size_t i = 0; i < input.size(); ++i)
            max_error = std::max(max_error, std::abs(int(input[i]) - int(output[i])));
        ok = max_error <= 2;
    }
    std::cout << "MUXMENDER_COLOR_TEST={\"ok\":" << (ok ? "true" : "false")
              << ",\"max_channel_error\":" << max_error
              << ",\"width\":64,\"height\":64,\"dolby_vision_tested\":false}\n";
    pl_tex_destroy(gpu, &target);
    pl_tex_destroy(gpu, &source);
    pl_renderer_destroy(&renderer);
    pl_d3d11_destroy(&device);
    pl_log_destroy(&log);
    std::cout << "Generated-color test [====================] 100%\n";
    return ok ? 0 : 4;
}
