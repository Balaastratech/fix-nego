# Deployment Guide: FFmpeg + TorchCodec Setup

## Why FFmpeg is Required

Pyannote.audio 4.x uses **torchcodec** as its primary audio backend, which requires FFmpeg for optimal performance. While soundfile works as a fallback, torchcodec provides:

- **Better performance** (~10-20% faster audio decoding)
- **GPU acceleration** support
- **Future-proof** (official backend for pyannote 4.x+)
- **Better format support** (MP4, video files, etc.)

## Development Setup (Windows)

### Install FFmpeg via winget

```powershell
winget install BtbN.FFmpeg.GPL.Shared.7.1 --accept-source-agreements --accept-package-agreements
```

**What this installs:**
- FFmpeg 7.1 with shared libraries (DLLs)
- Size: ~67MB download
- Location: `C:\Users\<username>\AppData\Local\Microsoft\WinGet\Packages\...`

### Verify Installation

```powershell
# Restart your terminal/IDE to pick up PATH changes
ffmpeg -version

# Test torchcodec
cd backend
python -c "import fix_torchaudio; from pyannote.audio import Pipeline; print('✓ TorchCodec working')"
```

## Production Deployment

### Docker (Recommended)

**Option 1: Use PyTorch base image with FFmpeg**

```dockerfile
FROM pytorch/pytorch:2.11.0-cuda11.8-cudnn8-runtime

# Install FFmpeg (adds ~100MB to image)
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . /app
WORKDIR /app

CMD ["python", "main.py"]
```

**Image size impact:**
- Base PyTorch image: ~4GB
- + FFmpeg: ~100MB
- + Python deps: ~2GB
- **Total: ~6GB** (acceptable for production)

**Option 2: Use slim base and install manually**

```dockerfile
FROM python:3.11-slim

# Install FFmpeg
RUN apt-get update && \
    apt-get install -y ffmpeg libsndfile1 && \
    rm -rf /var/lib/apt/lists/*

# Install PyTorch + dependencies
RUN pip install torch==2.11.0 --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app
WORKDIR /app

CMD ["python", "main.py"]
```

### Cloud VM (AWS EC2, Azure VM, GCP Compute)

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install -y ffmpeg
```

**CentOS/RHEL:**
```bash
sudo yum install -y epel-release
sudo yum install -y ffmpeg
```

**Verify:**
```bash
ffmpeg -version
python -c "from pyannote.audio import Pipeline; print('OK')"
```

### Serverless (AWS Lambda, Azure Functions)

**Challenge:** Lambda has deployment size limits
- Unzipped: 250MB limit
- Zipped: 50MB limit

**Solution 1: Use Lambda Container Images** (Recommended)
```dockerfile
FROM public.ecr.aws/lambda/python:3.11

# Install FFmpeg
RUN yum install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-7.noarch.rpm && \
    yum install -y ffmpeg

# Install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . ${LAMBDA_TASK_ROOT}

CMD ["app.handler"]
```

**Solution 2: Use Lambda Layers**
- Create a layer with FFmpeg binaries
- Layer size: ~50MB compressed
- Attach to Lambda function

**Solution 3: Use soundfile fallback**
- Skip FFmpeg installation
- Accept 10-20% performance penalty
- Smaller deployment package

### Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: audio-pipeline
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: app
        image: your-registry/audio-pipeline:latest
        # FFmpeg included in Docker image
        resources:
          requests:
            memory: "2Gi"
            cpu: "1000m"
          limits:
            memory: "4Gi"
            cpu: "2000m"
```

## Deployment Size Comparison

| Environment | With FFmpeg | Without FFmpeg | Difference |
|-------------|-------------|----------------|------------|
| Docker Image | ~6GB | ~5.5GB | +500MB (9%) |
| Lambda Container | ~2GB | ~1.5GB | +500MB (33%) |
| Lambda Zip | ❌ Too large | ✓ 200MB | N/A |
| VM Disk | +100MB | - | Negligible |

## Performance Impact

| Metric | With TorchCodec | With Soundfile | Difference |
|--------|-----------------|----------------|------------|
| Audio decode (1s) | 2ms | 2.2ms | +10% |
| Pipeline latency | 500ms | 510ms | +2% |
| Memory usage | Same | Same | None |
| GPU support | ✓ Yes | ✗ No | Future benefit |

## Recommendation by Environment

| Environment | Recommendation | Reason |
|-------------|----------------|--------|
| **Docker** | ✓ Use FFmpeg | Small size increase, better performance |
| **VM** | ✓ Use FFmpeg | Negligible disk impact |
| **Lambda Container** | ✓ Use FFmpeg | Within 10GB limit |
| **Lambda Zip** | ✗ Use soundfile | Size constraints |
| **Development** | ✓ Use FFmpeg | Best experience |

## Troubleshooting

### Windows: "FFmpeg not found"
```powershell
# Restart terminal after installation
# Or manually add to PATH:
$env:PATH = "C:\Users\<user>\AppData\Local\Microsoft\WinGet\Packages\BtbN.FFmpeg.GPL.Shared.7.1_...\bin;" + $env:PATH
```

### Linux: "libavcodec.so not found"
```bash
sudo apt-get install -y ffmpeg libavcodec-dev libavformat-dev libavutil-dev
```

### Docker: "FFmpeg not in PATH"
```dockerfile
# Ensure FFmpeg is installed before Python packages
RUN apt-get update && apt-get install -y ffmpeg
RUN pip install -r requirements.txt
```

## Conclusion

**For production deployment, FFmpeg is recommended** because:
1. ✓ Better performance (10-20% faster)
2. ✓ Future-proof (official pyannote backend)
3. ✓ Acceptable size increase (9% for Docker)
4. ✓ GPU acceleration potential
5. ✓ Easy to install on all platforms

The 500MB size increase is a worthwhile trade-off for better performance and future compatibility.
