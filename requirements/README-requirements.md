Requirements
This document describes how to set up the runtime environment for the project.
IMPORTANT:

requirements*.txt files contain ONLY external Python dependencies (PyPI).
Internal project modules (assault-env, assault-engine, etc.)
must be installed separately using pip install -e.


Base installation (CPU)

Create and activate a virtual environment:

python -m venv .venv
.venv\Scripts\activate

Install external dependencies:

pip install -r requirements/requirements-base.txt

Installation of internal project modules (mandatory)
This repository is organized as a monorepo containing multiple
internal Python projects. Each internal project must be installed
explicitly in editable mode.
From the project root directory (pry_ai):
pip install -e assault-engine
pip install -e .\assault_runner
pip install -e assault-env
If additional internal packages exist, install them the same way:
pip install -e assault-viewer
pip install -e assault-web
This step is mandatory to ensure that all internal imports work
correctly without using PYTHONPATH, wrapper scripts,
or special execution contexts.

GPU support (optional)
To enable GPU acceleration, the CUDA-enabled version of PyTorch must
be installed manually according to the local GPU and driver version.
Example for CUDA 11.8:
pip uninstall torch torchvision torchaudio -y
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
Verify GPU availability:
python -c "import torch; print(torch.cuda.is_available())"

Training execution
Once all external dependencies and internal project modules are installed,
training can be executed normally.
Basic execution:
python assault-env\train\train.py
If all internal packages are fully module-compliant, training can also
be executed using the module interface:
python -m assault_env.train.train
No additional environment configuration is required.

Summary

requirements*.txt files contain external PyPI dependencies only
Internal project modules must be installed using:
pip install -e 
Internal projects must never be listed inside requirements*.txt
This setup guarantees reproducible execution across environments
without relying on PYTHONPATH or ad-hoc scripts