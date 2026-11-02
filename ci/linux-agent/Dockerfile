FROM jenkins/inbound-agent:latest-jdk21

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv git binutils ca-certificates \
    libegl1 libgl1 libopengl0 libdbus-1-3 libxkbcommon0 \
    libfontconfig1 libglib2.0-0t64 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
USER jenkins
WORKDIR /home/jenkins/agent
ENV QT_QPA_PLATFORM=offscreen
