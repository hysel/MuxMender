FROM ghcr.io/linuxserver/ffmpeg:8.0.1-cli-ls61@sha256:81e11f5953179536ca3b478f406d77ae3f114ad72a6243d78ff2476a2b76eb3a
USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3 mkvtoolnix && apt-get clean
COPY vendor/hdr10plus.tar.gz /tmp/hdr10plus.tar.gz
RUN echo '06385f37a639d61ba21d4be3150c863846933bc3b58110e094d8fc8f1c2249f2  /tmp/hdr10plus.tar.gz' | sha256sum -c - && mkdir /opt/hdr10plus && tar -xzf /tmp/hdr10plus.tar.gz -C /opt/hdr10plus && chmod 755 /opt/hdr10plus/hdr10plus_tool
COPY python/ /opt/muxmender/
COPY tests/test_hdr10plus_validation.py tests/test_hdr10plus_preserve.py /opt/tests/
ENV PYTHONPATH=/opt/muxmender PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENV PATH=/opt/hdr10plus:$PATH
RUN python3 -B -m unittest discover -s /opt/tests && hdr10plus_tool --version && mkvmerge --version
USER 3005:3005
ENTRYPOINT ["python3", "-B", "-m", "hdr10plus_preserve"]
