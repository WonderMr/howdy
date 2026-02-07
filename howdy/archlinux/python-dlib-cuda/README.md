# python-dlib-cuda for Arch Linux

PKGBUILD for python-dlib with CUDA support, compatible with CUDA 13.x and cmake 4.x.

## Requirements

- NVIDIA GPU with compute capability >= 5.2 (Maxwell or newer)
- CUDA Toolkit 13.x
- cuDNN
- GCC 13 (CUDA 13.x is not compatible with GCC 14+)

## Installation

```bash
# Install dependencies
sudo pacman -S cuda cudnn cblas lapack cmake boost sqlite
yay -S gcc13  # Or install from AUR manually

# Build and install
cd howdy/archlinux/python-dlib-cuda
makepkg -si
```

## GPU Architecture Auto-Detection

The PKGBUILD automatically detects your GPU's compute capability using `nvidia-smi`.
If auto-detection fails, it defaults to `sm_86` (RTX 3000 series).

### Manual Override

To specify a different GPU architecture, set the environment variable before building:

```bash
DLIB_CUDA_COMPUTE_CAP=75 makepkg -si  # For RTX 2000 series (Turing)
DLIB_CUDA_COMPUTE_CAP=89 makepkg -si  # For RTX 4000 series (Ada)
```

### GPU Architecture Reference

| GPU Series | Architecture | Compute Capability |
|------------|--------------|-------------------|
| GTX 900 (Maxwell) | sm_52 | 52 |
| GTX 1000 (Pascal) | sm_61 | 61 |
| RTX 2000 (Turing) | sm_75 | 75 |
| RTX 3000 (Ampere) | sm_86 | 86 |
| RTX 4000 (Ada) | sm_89 | 89 |

Find your GPU's compute capability:
```bash
nvidia-smi --query-gpu=compute_cap --format=csv
```

## Fixes Applied (vs original AUR package)

1. **CUDA flag**: Explicitly passes `-DDLIB_USE_CUDA=ON` to cmake
2. **cmake 4.x compatibility**: Adds `CMAKE_POLICY_DEFAULT_CMP0146=OLD` (FindCUDA module was removed)
3. **GCC compatibility**: Uses GCC 13 via `CUDA_HOST_COMPILER=/usr/bin/gcc-13`
4. **Modern GPU support**: Configurable compute capability instead of hardcoded sm_50

## Verification

After installation, verify CUDA support:

```bash
python3 -c "import dlib; print('CUDA:', dlib.DLIB_USE_CUDA); print('AVX:', dlib.USE_AVX_INSTRUCTIONS)"
```

Expected output:
```
CUDA: True
AVX: True
```

## Troubleshooting

### "CUDA driver version is insufficient"
Ensure your NVIDIA driver is up to date: `sudo pacman -S nvidia nvidia-utils`

### Build fails with GCC errors
Verify gcc13 is installed: `pacman -Q gcc13`

### "Unsupported gpu architecture 'compute_50'"
Your CUDA version dropped support for sm_50. Use a newer GPU architecture or set `DLIB_CUDA_COMPUTE_CAP`.
