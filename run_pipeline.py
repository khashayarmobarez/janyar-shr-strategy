import subprocess
import sys
import time

STEPS = [
    "step1_extract.py",
    "step2_grouped.py",
    "step3_filtered.py",
    "step4_lists.py",
    "step5_rescore.py",
    "step6_drawdown.py",
    "step7_combine.py",
]


def run_pipeline():
    print("=" * 55)
    print("RUNNING FULL PIPELINE (steps 1 → 7)")
    print("=" * 55)

    pipeline_start = time.time()

    for i, script in enumerate(STEPS, start=1):
        print(f"\n[{i}/7] Running {script}...")
        step_start = time.time()

        result = subprocess.run(
            [sys.executable, script],
            capture_output=False,
        )

        elapsed = time.time() - step_start

        if result.returncode != 0:
            print(f"\nERROR: {script} failed (exit code {result.returncode}). Pipeline stopped.")
            sys.exit(result.returncode)

        print(f"[{i}/7] {script} done in {elapsed:.1f}s")

    total = time.time() - pipeline_start
    print(f"\n{'=' * 55}")
    print(f"PIPELINE COMPLETE — total time: {total:.1f}s")
    print(f"{'=' * 55}")


if __name__ == "__main__":
    run_pipeline()
