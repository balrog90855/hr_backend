OpenShift wheelhouse for the backend.

Target:
- Linux x86_64
- Python 3.10
- manylinux2014 / manylinux_2_17 compatible wheels

Install in an offline environment with:

```bash
pip install --no-index --find-links /path/to/wheelhouse/openshift-py310 -r requirements.txt
```

Notes:
- This wheelhouse was generated from the backend `requirements.txt` file.
- It is intended for Red Hat OpenShift style Linux deployments, not Windows.
- If the target cluster uses a different CPU architecture, build a separate wheelhouse for that architecture.