#!/bin/bash
# Reads the source only. All persistent writes are on the authorized destination.
set -euo pipefail
umask 077
tools_dir=$(cd -- "$(dirname -- "$0")" && pwd)
capture_id=$(date -u +%Y%m%dT%H%M%SZ)
for attempt in 1 2 3; do
  snapshot_dir="/opt/crm/migration/${capture_id}-${attempt}"
  ssh crm "umask 077; mkdir -p '$snapshot_dir'"
  ssh root@164.92.244.103 'python3 - --manifest-files /var/www/html/suitecrm/upload' < "$tools_dir/export.py" | ssh crm "umask 077; cat > '$snapshot_dir/upload-before.json'"
  ssh root@164.92.244.103 'bash -o pipefail -c "mysqldump --single-transaction --quick --skip-lock-tables --hex-blob --default-character-set=utf8mb4 suitecrmdb | gzip -c"' | ssh crm "umask 077; cat > '$snapshot_dir/source.sql.gz'"
  ssh root@164.92.244.103 'python3 - --archive-files /var/www/html/suitecrm/upload' < "$tools_dir/export.py" | gzip -c | ssh crm "umask 077; cat > '$snapshot_dir/upload.tar.gz'"
  ssh root@164.92.244.103 'python3 - --archive-metadata /var/www/html/suitecrm' < "$tools_dir/export.py" | gzip -c | ssh crm "umask 077; cat > '$snapshot_dir/metadata.tar.gz'"
  ssh root@164.92.244.103 'python3 - --safe-config /var/www/html/suitecrm' < "$tools_dir/export.py" | ssh crm "umask 077; cat > '$snapshot_dir/safe-config.json'"
  ssh root@164.92.244.103 'python3 - --manifest-files /var/www/html/suitecrm/upload' < "$tools_dir/export.py" | ssh crm "umask 077; cat > '$snapshot_dir/upload-after.json'"
  if ssh crm "cmp -s '$snapshot_dir/upload-before.json' '$snapshot_dir/upload-after.json'"; then
    scp "$tools_dir/export.py" "crm:$snapshot_dir/export-tool.py" >/dev/null
    ssh crm "python3 - '$snapshot_dir'" <<'PY'
import datetime,gzip,hashlib,json,os,pathlib,sys,tarfile
root=pathlib.Path(sys.argv[1]); os.umask(0o077)
# The source tar producer emits only regular files; validate again at the boundary.
for name in ('upload','metadata'):
    dest=root/name; dest.mkdir(mode=0o700,exist_ok=True)
    with tarfile.open(root/(name+'.tar.gz')) as archive:
        for member in archive:
            path=pathlib.Path(member.name)
            if not member.isfile() or path.is_absolute() or '..' in path.parts:
                raise ValueError('Unsafe source archive member')
            target=dest/path; target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            with archive.extractfile(member) as src, target.open('xb') as out:
                for block in iter(lambda:src.read(1024*1024),b''):out.write(block)
            target.chmod(0o600)
sys.path.insert(0,str(root))
import importlib.util
spec=importlib.util.spec_from_file_location('snapshot_export',root/'export-tool.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
before=json.loads((root/'upload-before.json').read_text())
module.check_files_unchanged(before,module.file_manifest(root/'upload'))
info={'source_key':'suitecrm-coloris','captured_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sql_sha256':module.digest_file(root/'source.sql.gz'),'files':before,'safe_config':json.loads((root/'safe-config.json').read_text()),'metadata_files':module.file_manifest(root/'metadata')}
(root/'capture-info.json').write_text(module.canonical_json(info));(root/'capture-info.json').chmod(0o600)
print('Captured consistent snapshot:',root,'files:',len(before),'SQL SHA256:',info['sql_sha256'])
PY
    exit 0
  fi
  printf 'Source upload changed; retaining incomplete attempt and retrying (%s/3)\n' "$attempt" >&2
done
printf 'Source files changed during all three capture attempts; no snapshot is ready.\n' >&2
exit 1
