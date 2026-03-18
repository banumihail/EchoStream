import torch
from transformers import pipeline
import os


def check_setup():
    print("--- VERIFICARE SETUP ---")
    # Verificăm placa video
    gpu_available = torch.cuda.is_available()
    print(f"1. Placa video detectată: {gpu_available}")
    if gpu_available:
        print(f"   Model: {torch.cuda.get_device_name(0)}")

    # Testăm un model mic de AI (Sentiment Analysis) ca să vedem că merg librăriile
    print("\n2. Testăm un model AI rapid...")
    classifier = pipeline("sentiment-analysis", device=0 if gpu_available else -1)
    res = classifier("I love building AI projects on my new desktop!")[0]
    print(f"   Rezultat test AI: {res['label']} (Scor: {res['score']:.2f})")


if __name__ == "__main__":
    check_setup()