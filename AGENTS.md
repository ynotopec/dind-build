# Repository guide

- Keep installation and removal scripts idempotent.
- Use `uv` for Python environments and dependency installation.
- Keep the virtual environment outside the repository at `~/venv/<project-name>`.
- Never commit `.env`, credentials, API tokens, kubeconfig files, or generated service units.
- Require an explicit Kubernetes namespace; do not introduce a namespace default.
- Keep HTTP endpoints authenticated and bound to loopback by default.
- Maintain compatibility with Linux on both `x86_64` and `aarch64` (including NVIDIA H100 hosts and DGX Spark).
- Run unit tests and shell syntax checks before committing.
