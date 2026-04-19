ARG BASE_IMAGE=ubuntu:20.04
FROM ${BASE_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive
ARG QUARTUS_INSTALL_DIR=/opt/intelFPGA_lite/17.0

RUN release="$(. /etc/os-release && printf '%s' "$VERSION_ID")" && \
    if [ "${release}" = "16.04" ]; then \
      sed -i 's|http://archive.ubuntu.com/ubuntu|http://old-releases.ubuntu.com/ubuntu|g; s|http://security.ubuntu.com/ubuntu|http://old-releases.ubuntu.com/ubuntu|g' /etc/apt/sources.list; \
    elif [ "${release}" = "18.04" ] || [ "${release}" = "20.04" ]; then \
      sed -i 's|http://security.ubuntu.com/ubuntu|http://archive.ubuntu.com/ubuntu|g' /etc/apt/sources.list; \
    fi && \
    apt-get update -o Acquire::Retries=5 && \
    apt-get install -y --no-install-recommends ca-certificates && \
    if [ "${release}" = "18.04" ] || [ "${release}" = "20.04" ]; then \
      sed -i 's|http://security.ubuntu.com/ubuntu|https://archive.ubuntu.com/ubuntu|g; s|http://archive.ubuntu.com/ubuntu|https://archive.ubuntu.com/ubuntu|g' /etc/apt/sources.list; \
    fi && \
    dpkg --add-architecture i386 && \
    apt-get update -o Acquire::Retries=5 && \
    apt-get install -y --no-install-recommends \
      file \
      libc6:i386 \
      libbz2-1.0:i386 \
      libfontconfig1 \
      libfreetype6:i386 \
      libglib2.0-0 \
      libglib2.0-0:i386 \
      libice6:i386 \
      locales \
      lsb-release \
      libncurses5:i386 \
      libsm6:i386 \
      libstdc++6:i386 \
      libx11-6:i386 \
      libxau6:i386 \
      libxcb1:i386 \
      libxdmcp6:i386 \
      libxext6:i386 \
      libxft2:i386 \
      libxrender1:i386 \
      libxt6:i386 \
      libxtst6:i386 \
      perl \
      python3 \
      tar \
      wget \
      xz-utils \
      zlib1g:i386 && \
    sed -i 's/^# *en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen && \
    locale-gen en_US.UTF-8 && \
    rm -rf /var/lib/apt/lists/*

COPY install-quartus.sh /tmp/install-quartus.sh
COPY installer/ /tmp/quartus-installer/

RUN chmod +x /tmp/install-quartus.sh && \
    /tmp/install-quartus.sh "${QUARTUS_INSTALL_DIR}" && \
    rm -rf /tmp/quartus-installer /tmp/install-quartus.sh

ENV QUARTUS_INSTALL_DIR=${QUARTUS_INSTALL_DIR}
ENV QUARTUS_ROOTDIR=${QUARTUS_INSTALL_DIR}/quartus
ENV PATH=${QUARTUS_INSTALL_DIR}/quartus/bin:${PATH}
ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8

WORKDIR /workspaces/3s-mister-arm
