#include <d3d11.h>
#include <dxgi1_2.h>
#include <windows.h>

#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>

namespace {

std::string json_escape(const std::string& value) {
    std::ostringstream escaped;
    for (const unsigned char character : value) {
        switch (character) {
        case '\\': escaped << "\\\\"; break;
        case '"': escaped << "\\\""; break;
        case '\b': escaped << "\\b"; break;
        case '\f': escaped << "\\f"; break;
        case '\n': escaped << "\\n"; break;
        case '\r': escaped << "\\r"; break;
        case '\t': escaped << "\\t"; break;
        default:
            if (character < 0x20) {
                escaped << "\\u" << std::hex << std::setw(4) << std::setfill('0')
                        << static_cast<int>(character) << std::dec;
            } else {
                escaped << character;
            }
        }
    }
    return escaped.str();
}

std::string utf8(const wchar_t* value) {
    if (!value || !*value) {
        return {};
    }
    const int required = WideCharToMultiByte(CP_UTF8, 0, value, -1, nullptr, 0, nullptr, nullptr);
    if (required <= 1) {
        return {};
    }
    std::string result(static_cast<size_t>(required), '\0');
    if (!WideCharToMultiByte(CP_UTF8, 0, value, -1, result.data(), required, nullptr, nullptr)) {
        return {};
    }
    result.resize(static_cast<size_t>(required - 1));
    return result;
}

std::string feature_level_name(const D3D_FEATURE_LEVEL level) {
    switch (level) {
    case D3D_FEATURE_LEVEL_12_2: return "12_2";
    case D3D_FEATURE_LEVEL_12_1: return "12_1";
    case D3D_FEATURE_LEVEL_12_0: return "12_0";
    case D3D_FEATURE_LEVEL_11_1: return "11_1";
    case D3D_FEATURE_LEVEL_11_0: return "11_0";
    default: return "unsupported";
    }
}

void emit_failure(const std::string& message, const HRESULT result) {
    std::cerr << "MUXMENDER_D3D11_PREFLIGHT={\"ok\":false,\"message\":\""
              << json_escape(message) << "\",\"hresult\":\"0x" << std::hex
              << std::uppercase << static_cast<unsigned long>(result) << "\"}\n";
}

} // namespace

int main() {
    const D3D_FEATURE_LEVEL requested_levels[] = {
        D3D_FEATURE_LEVEL_12_1,
        D3D_FEATURE_LEVEL_12_0,
        D3D_FEATURE_LEVEL_11_1,
        D3D_FEATURE_LEVEL_11_0,
    };

    ID3D11Device* device = nullptr;
    ID3D11DeviceContext* context = nullptr;
    D3D_FEATURE_LEVEL selected_level{};
    const HRESULT create_result = D3D11CreateDevice(
        nullptr,
        D3D_DRIVER_TYPE_HARDWARE,
        nullptr,
        0,
        requested_levels,
        static_cast<UINT>(std::size(requested_levels)),
        D3D11_SDK_VERSION,
        &device,
        &selected_level,
        &context);

    if (FAILED(create_result)) {
        emit_failure("Could not create a hardware D3D11 device", create_result);
        return 2;
    }

    IDXGIDevice* dxgi_device = nullptr;
    HRESULT result = device->QueryInterface(__uuidof(IDXGIDevice), reinterpret_cast<void**>(&dxgi_device));
    if (FAILED(result)) {
        emit_failure("Could not query the DXGI device", result);
        context->Release();
        device->Release();
        return 3;
    }

    IDXGIAdapter* adapter = nullptr;
    result = dxgi_device->GetAdapter(&adapter);
    if (FAILED(result)) {
        emit_failure("Could not identify the D3D11 adapter", result);
        dxgi_device->Release();
        context->Release();
        device->Release();
        return 4;
    }

    DXGI_ADAPTER_DESC description{};
    result = adapter->GetDesc(&description);
    if (FAILED(result)) {
        emit_failure("Could not read the D3D11 adapter description", result);
        adapter->Release();
        dxgi_device->Release();
        context->Release();
        device->Release();
        return 5;
    }

    const double dedicated_video_memory_gib =
        static_cast<double>(description.DedicatedVideoMemory) / (1024.0 * 1024.0 * 1024.0);
    std::cout << "MUXMENDER_D3D11_PREFLIGHT={\"ok\":true,\"adapter\":\""
              << json_escape(utf8(description.Description)) << "\",\"vendor_id\":\"0x"
              << std::hex << std::uppercase << description.VendorId << std::dec
              << "\",\"feature_level\":\"" << feature_level_name(selected_level)
              << "\",\"dedicated_video_memory_gib\":" << std::fixed << std::setprecision(2)
              << dedicated_video_memory_gib << "}\n";

    adapter->Release();
    dxgi_device->Release();
    context->Release();
    device->Release();
    return 0;
}
