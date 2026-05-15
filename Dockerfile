FROM ubuntu:22.04

# Set environment variables to avoid interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Shanghai

# Install system dependencies and useful tools
RUN apt-get update && apt-get install -y \
    # Python 3.10 and related tools (Ubuntu 22.04 comes with Python 3.10)
    python3.10 \
    python3.10-venv \
    python3.10-dev \
    python3-pip \
    python3-distutils \
    # Basic utilities
    curl \
    git \
    wget \
    vim \
    htop \
    tmux \
    gzip \
    tar \
    ca-certificates \
    # Network tools
    net-tools \
    iputils-ping \
    dnsutils \
    telnet \
    # Build tools (may be needed for some Python packages)
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create symbolic links for python and pip (force overwrite if exists)
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.10 1 \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1 \
    && ln -sf /usr/bin/pip3 /usr/bin/pip

# Upgrade pip to latest version
RUN python -m pip install --upgrade pip setuptools wheel

# Set working directory to /root/AlphaCrafter (home directory)
WORKDIR /root/AlphaCrafter

# Copy the entire current directory into the container
COPY . /root/AlphaCrafter/

# Install Python dependencies
RUN pip install --no-cache-dir \
    openai \
    python-dotenv \
    pydantic \
    requests \
    pyyaml \
    setuptools \
    pandas \
    numpy \
    scikit-learn \
    lightgbm

# Install PyTorch (CPU version - smaller footprint)
# For CUDA version, use the appropriate index URL
RUN pip install --no-cache-dir \
    torch \
    torchvision \
    torchaudio \
    --index-url https://download.pytorch.org/whl/cpu

# Optional: Install PyTorch with CUDA 11.8 support (uncomment if GPU available)
# RUN pip install --no-cache-dir \
#     torch \
#     torchvision \
#     torchaudio \
#     --index-url https://download.pytorch.org/whl/cu118

RUN pip install -e .

# Clean up apt cache to reduce image size
RUN apt-get clean && rm -rf /var/lib/apt/lists/*

# Set default command to bash
CMD ["/bin/bash"]