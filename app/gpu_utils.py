"""
GPU Utilities for MyFoil
Provides GPU detection and configuration management with automatic CPU fallback
"""

import os
import logging

logger = logging.getLogger("main")

# GPU Detection
HAS_CUDA = False
GPU_INFO = None

try:
    import cupy as cp
    if cp.cuda.is_available():
        HAS_CUDA = True
        device = cp.cuda.Device()
        GPU_INFO = {
            "name": device.name.decode() if isinstance(device.name, bytes) else str(device.name),
            "compute_capability": device.compute_capability,
            "memory_total": device.mem_info[1] / (1024**3),  # GB
            "memory_free": device.mem_info[0] / (1024**3),   # GB
        }
        logger.info(f"GPU detected: {GPU_INFO['name']} ({GPU_INFO['memory_total']:.1f} GB)")
    else:
        logger.info("CuPy installed but no CUDA-capable GPU detected")
except ImportError:
    logger.info("CuPy not installed - GPU acceleration disabled")
except Exception as e:
    logger.warning(f"Error detecting GPU: {e}")


def get_gpu_info():
    """
    Get information about available GPU
    
    Returns:
        dict: GPU information or None if no GPU available
    """
    return GPU_INFO


def is_gpu_available():
    """
    Check if GPU is available for use
    
    Returns:
        bool: True if GPU is available and enabled
    """
    return HAS_CUDA


def use_gpu_for_task(task_type):
    """
    Determine if GPU should be used for a specific task based on configuration
    
    Args:
        task_type (str): Type of task ('file_identification', 'image_processing', etc.)
        
    Returns:
        bool: True if GPU should be used for this task
    """
    # Check environment variable first (Docker configuration)
    env_gpu_enabled = os.environ.get("MYFOIL_GPU_ENABLED", "false").lower() == "true"
    
    if not env_gpu_enabled:
        return False
    
    if not HAS_CUDA:
        return False
    
    # Load settings to check task-specific configuration
    try:
        from settings import load_settings
        app_settings = load_settings()
        gpu_settings = app_settings.get("gpu", {})
        
        # Check if GPU is globally enabled
        if not gpu_settings.get("enabled", False):
            return False
        
        # Check task-specific setting
        task_settings = gpu_settings.get("tasks", {})
        return task_settings.get(task_type, False)
    except Exception as e:
        logger.debug(f"Error loading GPU settings: {e}")
        # Fallback to environment variable only
        return env_gpu_enabled and HAS_CUDA


def get_optimal_batch_size(task_type="default"):
    """
    Calculate optimal batch size based on available GPU memory
    
    Args:
        task_type (str): Type of task to optimize for
        
    Returns:
        int: Recommended batch size
    """
    if not HAS_CUDA or not GPU_INFO:
        return 1  # CPU fallback
    
    free_memory_gb = GPU_INFO.get("memory_free", 0)
    
    # Conservative estimates based on task type
    if task_type == "image_processing":
        # ~100MB per image in batch
        return max(1, int(free_memory_gb * 10))
    elif task_type == "file_identification":
        # ~50MB per file in batch
        return max(1, int(free_memory_gb * 20))
    else:
        return max(1, int(free_memory_gb * 5))


def log_gpu_status():
    """Log current GPU status for debugging"""
    if HAS_CUDA and GPU_INFO:
        logger.info(
            f"GPU Status: {GPU_INFO['name']} | "
            f"Memory: {GPU_INFO['memory_free']:.1f}/{GPU_INFO['memory_total']:.1f} GB free"
        )
    else:
        logger.info("GPU Status: Not available (using CPU)")
