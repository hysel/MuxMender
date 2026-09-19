# Build in an isolated container image; never apt-install on the TrueNAS host.
FROM ghcr.io/linuxserver/ffmpeg:8.0.1-cli-ls61@sha256:81e11f5953179536ca3b478f406d77ae3f114ad72a6243d78ff2476a2b76eb3a
USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3 && apt-get clean
COPY python/ /opt/muxmender/
ENV PYTHONPATH=/opt/muxmender PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 3005:3005
WORKDIR /output
ENTRYPOINT ["python3", "-B", "-m", "auto_optimize"]
