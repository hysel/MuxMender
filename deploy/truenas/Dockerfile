# Build in an isolated container image; never apt-install on the TrueNAS host.
FROM ghcr.io/hysel/muxmender@sha256:8990089f357812f3c1eed5b70461c4ccb1a44dd8ac8c251d82ba8b7a700f8df0
USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3 tini && apt-get clean
COPY python/ /opt/muxmender/
ENV PYTHONPATH=/opt/muxmender:/opt/muxmender-runtime PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 3005:3005
WORKDIR /output
ENTRYPOINT ["/usr/bin/tini", "--", "python3", "-B", "-m", "auto_optimize"]
