# Generic app image: GPU devices and folders are assigned by TrueNAS, not here.
FROM ghcr.io/linuxserver/ffmpeg:8.0.1-cli-ls61@sha256:81e11f5953179536ca3b478f406d77ae3f114ad72a6243d78ff2476a2b76eb3a
USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3 mkvtoolnix && apt-get clean
COPY vendor/hdr10plus.tar.gz /tmp/hdr10plus.tar.gz
COPY vendor/dovi.tar.gz /tmp/dovi.tar.gz
RUN echo '5dae82cb2becd3b9fd726127f936a8d32635e60746d16238fdfded12aa05988c  /tmp/dovi.tar.gz' | sha256sum -c - && mkdir /opt/dovi && tar -xzf /tmp/dovi.tar.gz -C /opt/dovi && chmod 755 /opt/dovi/dovi_tool
RUN echo '06385f37a639d61ba21d4be3150c863846933bc3b58110e094d8fc8f1c2249f2  /tmp/hdr10plus.tar.gz' | sha256sum -c - && mkdir /opt/hdr10plus && tar -xzf /tmp/hdr10plus.tar.gz -C /opt/hdr10plus && chmod 755 /opt/hdr10plus/hdr10plus_tool
COPY python/ /opt/muxmender/
ENV PYTHONPATH=/opt/muxmender PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENV PATH=/opt/dovi:/opt/hdr10plus:$PATH
RUN python3 -B -c "import hdr_auto, hdr10plus_preserve, dv_workflow" && hdr10plus_tool --version && dovi_tool --version && mkvmerge --version
ENV NVIDIA_DRIVER_CAPABILITIES=compute,video,utility
USER 568:568
EXPOSE 8765
ENTRYPOINT ["python3", "-B", "-m", "app_service"]
