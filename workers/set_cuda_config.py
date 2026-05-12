"""
PyTorch CUDA allocator configuration.
Must be imported BEFORE torch in any worker that runs on GPU. Reduces
fragmentation when multiple worker processes share the same physical GPU.
expandable_segments is Linux-only; on Windows we use max_split_size_mb +
garbage_collection_threshold which are universally supported.
"""
import os

os.environ.setdefault(
    "PYTORCH_CUDA_ALLOC_CONF",
    "max_split_size_mb:128,garbage_collection_threshold:0.6",
)
print(f"[Config] PYTORCH_CUDA_ALLOC_CONF={os.environ['PYTORCH_CUDA_ALLOC_CONF']}")
