# Generic app image: GPU devices and folders are assigned by TrueNAS, not here.
FROM ghcr.io/linuxserver/ffmpeg:8.0.1-cli-ls61@sha256:81e11f5953179536ca3b478f406d77ae3f114ad72a6243d78ff2476a2b76eb3a
USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3 && apt-get clean
COPY python/ /opt/muxmender/
ENV PYTHONPATH=/opt/muxmender PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENV NVIDIA_DRIVER_CAPABILITIES=compute,video,utility
USER 568:568
EXPOSE 8765
ENTRYPOINT ["python3", "-B", "-m", "app_service"]
