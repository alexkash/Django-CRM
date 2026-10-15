import subprocess,json,re,pathlib,hashlib,datetime
schema='suitecrmdb'
def rows(sql):
    r=subprocess.run(['mysql','--batch','--skip-column-names','--raw',schema],input='SET SESSION TRANSACTION READ ONLY;\n'+sql,text=True,capture_output=True,check=True)
    return [json.loads(line) for line in r.stdout.splitlines() if line]
columns=rows("SELECT JSON_OBJECT('table',TABLE_NAME,'column',COLUMN_NAME,'type',COLUMN_TYPE,'nullable',IS_NULLABLE,'key',COLUMN_KEY,'max_length',CHARACTER_MAXIMUM_LENGTH,'ordinal',ORDINAL_POSITION) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() ORDER BY TABLE_NAME,ORDINAL_POSITION;")
bytable={}
for col in columns: bytable.setdefault(col['table'],[]).append(col['column'])
queries=[]
for table,cols in sorted(bytable.items()):
    if not re.fullmatch('[a-zA-Z0-9_]+',table): raise ValueError('Unexpected table identifier')
    active='COALESCE(SUM(deleted=0),0)' if 'deleted' in cols else 'COUNT(*)'
    deleted='COALESCE(SUM(deleted<>0),0)' if 'deleted' in cols else '0'
    invalid="COALESCE(SUM(id IS NOT NULL AND id NOT REGEXP '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'),0)" if 'id' in cols else '0'
    queries.append(f"SELECT JSON_OBJECT('table','{table}','total',COUNT(*),'active',{active},'deleted',{deleted},'non_uuid_ids',{invalid}) FROM `{table}`")
counts=rows('START TRANSACTION WITH CONSISTENT SNAPSHOT;\n'+' UNION ALL '.join(queries)+';\nCOMMIT;')
custom=rows("SELECT JSON_OBJECT('module',custom_module,'name',name,'type',type,'length',len,'required',required,'deleted',deleted) FROM fields_meta_data ORDER BY custom_module,name;")
root=pathlib.Path('/var/www/html/suitecrm')
files=[]
for path in sorted((root/'upload').rglob('*')):
    if not path.is_file(): continue
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    files.append({'size':path.stat().st_size,'sha256':digest,'name_sha256':hashlib.sha256(str(path.relative_to(root/'upload')).encode()).hexdigest()})
filechecks=[]
for record in rows("SELECT JSON_OBJECT('id',id,'filename',filename,'deleted',deleted) FROM notes WHERE filename IS NOT NULL AND filename<>'';"):
    key=record['id']
    if not re.fullmatch('[a-zA-Z0-9_-]+',key):
        filechecks.append({'deleted':record['deleted'],'safe_file_key':False,'exists':False});continue
    path=root/'upload'/key
    filechecks.append({'deleted':record['deleted'],'safe_file_key':True,'exists':path.is_file()})
print(json.dumps({'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'server':'164.92.244.103','database':schema,'suitecrm_version':'7.12.6','schema':columns,'counts_snapshot':counts,'custom_fields':custom,'uploads':{'count':len(files),'bytes':sum(x['size'] for x in files),'hash_manifest':files,'note_file_reference_checks':filechecks}},ensure_ascii=False,indent=2))
