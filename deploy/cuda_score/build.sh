#!/bin/bash
set -euo pipefail
cd /build
# Reuse the same pinned FFmpeg/VMAF inputs as the canonical CPU runtime.
sha256sum -c source/source.sha256
tar -xf source/vmaf-3.0.0.tar.gz
python3 patches/apply_cuda_ptx_fix.py vmaf-3.0.0
python3 patches/apply_cuda_adm_fix.py vmaf-3.0.0
tar -xf source/ffmpeg-9.0.2.tar.xz
python3 patches/enable_cuda_10bit.py ffmpeg-9.0.2
tar -xf source/nv-codec-headers-n13.0.19.0.tar.gz
make -C nv-codec-headers-n13.0.19.0 install
export PATH=/usr/local/cuda/bin:$PATH
export LIBRARY_PATH=/usr/local/cuda/lib64/stubs:/usr/local/cuda/lib64
export PKG_CONFIG_PATH=/opt/muxmender-score/lib/pkgconfig
meson setup vmaf-3.0.0/libvmaf/build vmaf-3.0.0/libvmaf --prefix=/opt/muxmender-score --libdir=lib --buildtype=release -Denable_cuda=true -Denable_tests=false -Denable_docs=false -Dbuilt_in_models=true
ninja -C vmaf-3.0.0/libvmaf/build -j2
ninja -C vmaf-3.0.0/libvmaf/build install
ln -s /usr/local/cuda/lib64/stubs/libcuda.so /opt/muxmender-score/lib/libcuda.so.1
cd ffmpeg-9.0.2
# Private library RPATH must precede the CPU app's LD_LIBRARY_PATH. Otherwise
# the two libvmaf builds have the same SONAME and CUDA can load the CPU library.
./configure --prefix=/opt/muxmender-score --disable-autodetect --disable-doc --disable-debug --disable-ffplay --disable-network --disable-everything --enable-ffmpeg --enable-pthreads --enable-gpl --enable-version3 --enable-libvmaf --enable-libzimg --enable-libdav1d --enable-ffnvcodec --enable-cuda --enable-decoder=h264,hevc,av1,ffv1,rawvideo,libdav1d --enable-parser=h264,hevc,av1 --enable-demuxer=matroska --enable-muxer=null --enable-encoder=wrapped_avframe --enable-filter=buffer,buffersink,null,format,scale,split,libvmaf,libvmaf_cuda,hwupload_cuda,settb,setpts,zscale,tonemap --enable-protocol=file,pipe --extra-cflags=-I/opt/muxmender-score/include --extra-ldflags='-L/opt/muxmender-score/lib -L/usr/local/cuda/lib64/stubs -Wl,--disable-new-dtags,-rpath,/opt/muxmender-score/lib'
make -j2
make install
rm /opt/muxmender-score/lib/libcuda.so.1
# Only executable/runtime libraries and notices enter the final image.
mkdir -p /export/bin /export/lib /export/share/notices
cp /opt/muxmender-score/bin/ffmpeg /export/bin/
cp -a /opt/muxmender-score/lib/libvmaf.so* /export/lib/
cp COPYING.GPLv3 /export/share/notices/FFmpeg-GPLv3.txt
cp /build/vmaf-3.0.0/LICENSE /export/share/notices/VMAF-LICENSE.txt
# The CUDA compiler/SDK and its libraries are not copied into the app image.
