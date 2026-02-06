# MyFoil GPU Support

MyFoil now supports optional GPU acceleration for compute-intensive tasks.

## Requirements

- NVIDIA GPU with CUDA support
- Docker with NVIDIA Container Toolkit installed
- At least 4GB of GPU memory recommended

## Quick Start

### 1. Install NVIDIA Container Toolkit

```bash
# Ubuntu/Debian
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list

sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

### 2. Verify GPU Access

```bash
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi
```

### 3. Deploy with GPU Support

**Option A: Use GPU-enabled Docker Compose**

```bash
# Edit docker-compose.gpu.yml and update volume paths
docker-compose -f docker-compose.gpu.yml up -d
```

**Option B: Build GPU-enabled image**

```bash
# Build with GPU support
docker build -f Dockerfile.gpu -t myfoil:gpu .

# Run with GPU
docker run --gpus all -p 8465:8465 \
  -e MYFOIL_GPU_ENABLED=true \
  -v /path/to/games:/games \
  -v ./config:/app/config \
  myfoil:gpu
```

## Configuration

### Environment Variables

- `MYFOIL_GPU_ENABLED`: Set to `true` to enable GPU acceleration (default: `false`)

### Settings (config/settings.yaml)

```yaml
gpu:
  enabled: false  # Master switch for GPU features
  tasks:
    file_identification: false  # GPU-accelerated file identification (experimental)
    image_processing: false     # GPU-accelerated image processing
  fallback_to_cpu: true         # Always fallback to CPU if GPU fails
```

## Features

### Currently Supported

- **GPU Detection**: Automatic detection with graceful CPU fallback
- **Configuration Management**: Docker environment variables + YAML settings
- **Infrastructure**: Ready for GPU-accelerated tasks

### Planned Features

- **Image Processing**: GPU-accelerated thumbnail generation and image resizing
- **Batch Operations**: Parallel processing of multiple files
- **File Identification**: GPU-accelerated cryptographic operations (experimental)

## Troubleshooting

### GPU Not Detected

1. Check if GPU is visible: `nvidia-smi`
2. Verify Docker has GPU access: `docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi`
3. Check container logs: `docker logs myfoil`
4. Look for "GPU detected" message in logs

### Performance Not Improved

- GPU acceleration only helps with large batches (500+ files)
- Ensure `MYFOIL_GPU_ENABLED=true` is set
- Check that specific tasks are enabled in `settings.yaml`
- Small libraries may be faster on CPU due to GPU overhead

### CuPy Installation Failed

This is normal if no CUDA runtime is present. MyFoil will automatically fall back to CPU mode.

## CPU-Only Deployment

To deploy without GPU support, use the standard Docker Compose:

```bash
docker-compose up -d
```

GPU dependencies will not be installed, and all operations will run on CPU.
