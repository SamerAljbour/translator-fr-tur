"""Download only the Argos models required by the Tolba service."""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from pathlib import Path

# Keep build artifacts inside the repository so Render carries them from the
# build phase into the runtime image. This must be set before importing Argos.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("ARGOS_PACKAGES_DIR", str(_PROJECT_ROOT / ".argos-packages"))
os.environ.setdefault("XDG_DATA_HOME", str(_PROJECT_ROOT / ".argos-data"))
os.environ.setdefault("XDG_CACHE_HOME", str(_PROJECT_ROOT / ".argos-cache"))
os.environ.setdefault("XDG_CONFIG_HOME", str(_PROJECT_ROOT / ".argos-config"))

from argostranslate import package
from minisbd import download_models
from minisbd import models as minisbd_models
from packaging.version import Version

minisbd_models.cache_dir = str(_PROJECT_ROOT / ".minisbd")


REQUIRED_PAIRS = {
    ("ar", "en"),
    ("en", "ar"),
    ("en", "fr"),
    ("fr", "en"),
    ("en", "tr"),
    ("tr", "en"),
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s model-setup: %(message)s",
)
logger = logging.getLogger("model-setup")


def pair(model) -> tuple[str, str]:
    return model.from_code, model.to_code


def main() -> None:
    logger.info("Updating the Argos model index")
    package.update_package_index()

    candidates = defaultdict(list)
    for model in package.get_available_packages():
        if pair(model) in REQUIRED_PAIRS:
            candidates[pair(model)].append(model)

    unavailable = REQUIRED_PAIRS - candidates.keys()
    if unavailable:
        missing = ", ".join(f"{source}->{target}" for source, target in sorted(unavailable))
        raise RuntimeError(f"Required models are unavailable: {missing}")

    installed = {pair(model): model for model in package.get_installed_packages()}
    for language_pair in sorted(REQUIRED_PAIRS):
        selected = max(
            candidates[language_pair], key=lambda model: Version(model.package_version)
        )
        current = installed.get(language_pair)

        if current and Version(current.package_version) >= Version(selected.package_version):
            logger.info(
                "Model %s->%s version %s is already installed",
                *language_pair,
                current.package_version,
            )
            continue

        logger.info(
            "Installing model %s->%s version %s",
            *language_pair,
            selected.package_version,
        )
        if current:
            package.uninstall(current)
        package.install_from_path(selected.download())

    installed_pairs = {pair(model) for model in package.get_installed_packages()}
    missing = REQUIRED_PAIRS - installed_pairs
    unexpected = installed_pairs - REQUIRED_PAIRS
    if missing:
        raise RuntimeError(f"Model installation incomplete: {sorted(missing)}")
    if unexpected:
        raise RuntimeError(f"Unexpected models installed: {sorted(unexpected)}")

    logger.info("Preparing MiniSBD sentence-boundary models")
    download_models(["en", "ar", "fr", "tr"], logger.info)
    logger.info("All six required translation models are installed")


if __name__ == "__main__":
    main()
