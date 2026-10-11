# Generic app image: GPU devices and folders are assigned by TrueNAS, not here.
FROM ghcr.io/linuxserver/ffmpeg:8.0.1-cli-ls61@sha256:81e11f5953179536ca3b478f406d77ae3f114ad72a6243d78ff2476a2b76eb3a AS ffmpeg9-build
USER root
RUN apt-get update && apt-get install -y --no-install-recommends build-essential pkg-config nasm xz-utils xxd meson ninja-build python3-jinja2 zlib1g-dev libdav1d-dev libx264-dev libx265-dev libaom-dev libzimg-dev libass-dev libshaderc-dev libvulkan-dev && apt-get clean
COPY vendor/ffmpeg9-source/ /build/source/
COPY deploy/truenas/build_ffmpeg9.sh /build/build_ffmpeg9.sh
RUN bash /build/build_ffmpeg9.sh
FROM ghcr.io/linuxserver/ffmpeg:8.0.1-cli-ls61@sha256:81e11f5953179536ca3b478f406d77ae3f114ad72a6243d78ff2476a2b76eb3a
USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip mkvtoolnix libzstd1 tini libdav1d7 libx264-164 libx265-199 libaom3 libzimg2 libass9 libshaderc1 libvulkan1 && apt-get clean
COPY --from=ffmpeg9-build /opt/ffmpeg9/ /opt/ffmpeg9/
COPY --from=ffmpeg9-build /opt/ffmpeg9-deps/lib/ /opt/ffmpeg9-deps/lib/
ENV LD_LIBRARY_PATH=/opt/ffmpeg9-deps/lib:/usr/lib/x86_64-linux-gnu
LABEL org.muxmender.ffmpeg.version="9.0.2"
COPY deploy/truenas/requirements-av1-runtime.txt /tmp/requirements-av1-runtime.txt
RUN python3 -m pip install --no-cache-dir --no-deps --only-binary=:all: --require-hashes --target /opt/muxmender-runtime -r /tmp/requirements-av1-runtime.txt
COPY vendor/hdr10plus.tar.gz /tmp/hdr10plus.tar.gz
COPY vendor/dovi.tar.gz /tmp/dovi.tar.gz
RUN echo '5dae82cb2becd3b9fd726127f936a8d32635e60746d16238fdfded12aa05988c  /tmp/dovi.tar.gz' | sha256sum -c - && mkdir /opt/dovi && tar -xzf /tmp/dovi.tar.gz -C /opt/dovi && chmod 755 /opt/dovi/dovi_tool
RUN echo '06385f37a639d61ba21d4be3150c863846933bc3b58110e094d8fc8f1c2249f2  /tmp/hdr10plus.tar.gz' | sha256sum -c - && mkdir /opt/hdr10plus && tar -xzf /tmp/hdr10plus.tar.gz -C /opt/hdr10plus && chmod 755 /opt/hdr10plus/hdr10plus_tool
COPY python/ /opt/muxmender/
COPY vendor/gpu-reader/ /opt/muxmender-readers/
RUN if [ -f /opt/muxmender-readers/ffprobe-cuda ]; then chmod 0555 /opt/muxmender-readers/ffprobe-cuda; fi
ENV PYTHONPATH=/opt/muxmender:/opt/muxmender-runtime PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENV PATH=/opt/ffmpeg9/bin:/opt/dovi:/opt/hdr10plus:$PATH
COPY vendor/fel-runtime-archives/ /tmp/fel-runtime-archives/
COPY tools/install_fel_runtime.py /opt/muxmender-tools/install_fel_runtime.py
RUN python3 -B /opt/muxmender-tools/install_fel_runtime.py --archives /tmp/fel-runtime-archives --destination /opt/muxmender/runtime/felbaker --execute
RUN python3 -B -c "import hdr_auto, hdr10plus_preserve, dv_workflow, av1_content_light; assert av1_content_light.available()" && hdr10plus_tool --version && dovi_tool --version && mkvmerge --version
ENV NVIDIA_DRIVER_CAPABILITIES=compute,video,utility,graphics
USER 568:568
EXPOSE 8765
# Reap orphaned workers even when the app is installed without Compose init:true.
# Forward signals to the service, which owns cancellation of its worker groups.
ENTRYPOINT ["/usr/bin/tini", "--", "python3", "-B", "-m", "app_service"]
