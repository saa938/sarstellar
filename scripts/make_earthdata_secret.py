"""Create the Modal secret `earthdata` from the NASA login in ~/_netrc.

    python scripts/make_earthdata_secret.py [--force]

Reads the `urs.earthdata.nasa.gov` entry of ~/_netrc (~/.netrc if that is the one you have) and
runs `modal secret create earthdata EARTHDATA_USERNAME=... EARTHDATA_PASSWORD=...`. The values go
to Modal as arguments of a subprocess; they are never printed, logged or written anywhere else.
`--force` replaces an existing secret of that name. Only the secret `earthdata` is touched.
"""

from __future__ import annotations

import argparse
import netrc
import subprocess
import sys
from pathlib import Path

HOST = "urs.earthdata.nasa.gov"
SECRET = "earthdata"


def netrc_path() -> Path:
    home = Path.home()
    for name in ("_netrc", ".netrc"):
        if (home / name).is_file():
            return home / name
    raise SystemExit("No ~/_netrc (or ~/.netrc) found.")


def read_login(path: Path) -> tuple[str, str]:
    """(username, password) of the Earthdata entry. Never prints either."""
    try:
        entry = netrc.netrc(str(path)).authenticators(HOST)
    except (netrc.NetrcParseError, OSError) as exc:
        raise SystemExit(f"Could not read {path.name}: {type(exc).__name__}") from None
    if not entry or not entry[0] or not entry[2]:
        raise SystemExit(f"{path.name} has no {HOST} login.")
    return entry[0], entry[2]


def build_command(username: str, password: str, force: bool) -> list[str]:
    cmd = [sys.executable, "-m", "modal", "secret", "create", SECRET,
           f"EARTHDATA_USERNAME={username}", f"EARTHDATA_PASSWORD={password}"]
    return cmd + ["--force"] if force else cmd


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="replace an existing secret")
    args = parser.parse_args(argv)
    username, password = read_login(netrc_path())
    done = subprocess.run(build_command(username, password, args.force),
                          capture_output=True, text=True, check=False)
    if done.returncode == 0:
        print(f"Created Modal secret '{SECRET}'.")
        return 0
    detail = (done.stderr or done.stdout or "").replace(username, "***").replace(password, "***")
    print(f"modal secret create failed (exit {done.returncode}): {detail.strip()[-300:]}")
    return done.returncode


if __name__ == "__main__":
    raise SystemExit(main())
