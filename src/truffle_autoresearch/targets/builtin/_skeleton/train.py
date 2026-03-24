"""Minimal training script template.

Replace this with your actual training code. The script should:
1. Train a model (or run your experiment)
2. Print a metric line matching the pattern in target.yaml

The output format below matches the default skeleton target.yaml pattern:
    score:\s+(\d+\.\d+)
"""

import time


def main():
    # -- Replace everything below with your actual training code --

    print("Training...")
    time.sleep(1)

    # Compute your metric here
    score = 1.0

    # Print results — the metric line must match the pattern in target.yaml
    print("---")
    print(f"score:            {score:.6f}")


if __name__ == "__main__":
    main()
