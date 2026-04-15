"""
Configure Hugging Face cache directory to use D drive instead of C
Import this at the start of workers before loading models
"""
import os

# Set Hugging Face cache to D drive
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
model_cache_dir = os.path.join(project_root, "models_cache")

# Create directory if it doesn't exist
os.makedirs(model_cache_dir, exist_ok=True)

# Set environment variables for Hugging Face
os.environ["HF_HOME"] = model_cache_dir
os.environ["TRANSFORMERS_CACHE"] = model_cache_dir
os.environ["HF_DATASETS_CACHE"] = model_cache_dir

print(f"[Config] Model cache set to: {model_cache_dir}")
