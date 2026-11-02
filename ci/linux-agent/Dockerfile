FROM jenkins/inbound-agent:latest-jdk21

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv libpython3.13 git binutils ca-certificates \
    libegl1 libgl1 libopengl0 libdbus-1-3 libxkbcommon0 \
    libfontconfig1 libglib2.0-0t64 fonts-dejavu-core \
    libgtk-3-0t64 libxkbcommon-x11-0 libxcb-cursor0 \
    libxcb-icccm4 libxcb-keysyms1 libxcb-shape0 \
    libxcb-xinerama0 libxcb-randr0 xvfb xauth \
    && rm -rf /var/lib/apt/lists/*
USER jenkins
WORKDIR /home/jenkins/agent
ENV QT_QPA_PLATFORM=offscreen
