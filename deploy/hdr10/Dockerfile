FROM muxmender-hdr10plus-test:20260919-standalone1
USER root
COPY python/ /opt/muxmender/
COPY tests/ /opt/hdr10-tests/
RUN python3 -B -m unittest discover -s /opt/hdr10-tests
ENV NVIDIA_DRIVER_CAPABILITIES=compute,video,utility
USER 3005:3005
ENTRYPOINT ["python3", "-B", "-m", "hdr10_trial"]
