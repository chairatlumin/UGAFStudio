from __future__ import annotations

import argparse

from qa_framework.core.build import discover_build


def main() -> int:
    parser = argparse.ArgumentParser(description="UGAF Build QA Runner")

    parser.add_argument(
        "--build",
        required=True,
        help="Path to the game build directory",
    )

    args = parser.parse_args()

    print("=== UGAF BUILD QA ===")

    try:
        build = discover_build(args.build)

    except Exception as exc:
        print(f"BUILD DISCOVERY FAILED: {exc}")
        return 1

    print(f"Build Name : {build.name}")
    print(f"Build Root : {build.root}")
    print(f"Executable : {build.executable}")
    print("Status     : READY")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
