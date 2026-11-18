# Assembly fixture reproductions

These use the controller's existing benign `AssembleTest` fixture, which creates an isolated Git repository and fake archive under `.work/tmp`. They exercise assembly, not a native Node build or the hosted release workflow. Run each from the repository root with the checked-in Python environment.

## Stale build provenance

```sh
uv run --frozen python - <<'PY'
import json, subprocess
from tests.test_release import AssembleTest, TRIPLE
from buildsys import product, release
case = AssembleTest(); case.setUp()
try:
    root = case.work
    old = case.revision
    receipt = root / 'build' / TRIPLE / 'build-receipt.json'
    receipt.write_text(json.dumps({'source': {'revision': old}}))
    (root / 'sources.lock.json').write_text('{"schema_version": 1, "revision": "new"}\n')
    subprocess.run(['git', 'add', 'sources.lock.json'], cwd=root, check=True)
    subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'change lock'], cwd=root, check=True)
    current = release.git_revision(root)
    release.assemble_all(root, (TRIPLE,))
    manifest = json.loads((root / 'dist' / 'release' / product.manifest_name(product.NODE_VERSION, TRIPLE)).read_text())
    assert old != current and manifest['source_revision'] == current
    assert manifest['source']['revision'] == old
    print('assembled old receipt under current revision:', old != current)
finally:
    case.cleanup()
PY
```

Expected observed output: `assembled old receipt under current revision: True`. The fixture labels the receipt's source with an artificial revision marker to make the mismatch visible; real receipts do not record the controller revision. The result demonstrates the missing linkage, not that the hosted workflow mixed artifacts.

## Empty qualification

```sh
uv run --frozen python - <<'PY'
import json
from tests.test_release import AssembleTest, TRIPLE
from buildsys import product, release
case = AssembleTest(); case.setUp()
try:
    root = case.work
    path = root / 'build' / TRIPLE / 'qualify' / 'qualify-record.json'
    record = json.loads(path.read_text())
    record.update(product_checks=[], smoke=[], relocation=[], smoke_passed=0, smoke_total=0)
    path.write_text(json.dumps(record))
    release.assemble_all(root, (TRIPLE,))
    manifest = json.loads((root / 'dist' / 'release' / product.manifest_name(product.NODE_VERSION, TRIPLE)).read_text())
    assert manifest['qualification']['smoke_total'] == 0
    assert manifest['qualification']['product_checks'] == []
    print('assembled with no qualification checks: True')
finally:
    case.cleanup()
PY
```

Expected observed output: `assembled with no qualification checks: True`. This checks acceptance of an incomplete record, not a claim that the normal qualifier generates one.
