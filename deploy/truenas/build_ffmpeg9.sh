#!/bin/bash
set -euo pipefail
cd /build
sha256sum -c source/source.sha256
tar -xf source/ffmpeg-9.0.2.tar.xz
tar -xf source/nv-codec-headers-n13.0.19.0.tar.gz
tar -xf source/vmaf-3.0.0.tar.gz
tar -xf source/libplacebo-7.351.0.tar.gz
tar -xf source/vulkan-headers-libplacebo.tar.gz -C libplacebo-7.351.0/3rdparty/Vulkan-Headers --strip-components=1
make -C nv-codec-headers-n13.0.19.0 install
command -v xxd
meson setup vmaf-3.0.0/libvmaf/build vmaf-3.0.0/libvmaf --prefix=/opt/ffmpeg9-deps --libdir=lib --buildtype=release -Dbuilt_in_models=true -Denable_tests=false -Denable_docs=false
ninja -C vmaf-3.0.0/libvmaf/build -j2
ninja -C vmaf-3.0.0/libvmaf/build install
export PKG_CONFIG_PATH=/opt/ffmpeg9-deps/lib/pkgconfig:/usr/lib/x86_64-linux-gnu/pkgconfig:/usr/share/pkgconfig
meson setup libplacebo-7.351.0/build libplacebo-7.351.0 --prefix=/opt/ffmpeg9-deps --libdir=lib --buildtype=release -Dvulkan=enabled -Dshaderc=enabled -Dglslang=disabled -Dopengl=disabled -Ddemos=false -Dtests=false -Dlibdovi=disabled
ninja -C libplacebo-7.351.0/build -j2
ninja -C libplacebo-7.351.0/build install
mkdir -p /opt/ffmpeg9-deps/include
cp -r libplacebo-7.351.0/3rdparty/Vulkan-Headers/include/. /opt/ffmpeg9-deps/include/
cd ffmpeg-9.0.2
./configure --prefix=/opt/ffmpeg9 --disable-autodetect --disable-doc --disable-debug --disable-ffplay --disable-network --enable-gpl --enable-version3 --enable-pthreads --enable-zlib --enable-libdav1d --enable-libx264 --enable-libx265 --enable-libaom --enable-libvmaf --enable-libzimg --enable-libass --enable-libplacebo --enable-vulkan --enable-ffnvcodec --enable-nvenc --enable-nvdec --enable-cuvid --enable-cuda --extra-cflags='-I/opt/ffmpeg9-deps/include' --extra-ldflags='-L/opt/ffmpeg9-deps/lib -L/usr/lib/x86_64-linux-gnu -Wl,-rpath,/opt/ffmpeg9-deps/lib'
make -j2
make install
LD_LIBRARY_PATH=/opt/ffmpeg9-deps/lib:/usr/lib/x86_64-linux-gnu /opt/ffmpeg9/bin/ffmpeg -v error -nostdin -f lavfi -i 'testsrc2=size=192x108:rate=2:duration=1' -filter_complex '[0:v]split[a][b];[a][b]libvmaf=n_threads=2' -f null -
