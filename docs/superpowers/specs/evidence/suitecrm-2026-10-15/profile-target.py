import json,datetime,django
django.setup()
from django.apps import apps
wanted={'User','Profile','Org','Account','Contact','Lead','Opportunity','Task','Activity','Comment','AccountEmail','AccountEmailLog','EmailMessage','Invoice','InvoiceLineItem','Product','Estimate','Payment','Document','Attachments','CustomFieldDefinition'}
result={}
for model in apps.get_models():
    if model.__name__ not in wanted: continue
    fields=[]
    for f in model._meta.get_fields():
        if f.auto_created and not f.concrete:continue
        fields.append({'name':f.name,'type':type(f).__name__,'null':getattr(f,'null',None),'max_length':getattr(f,'max_length',None),'unique':getattr(f,'unique',None),'related_model':f.related_model._meta.label if getattr(f,'related_model',None) else None,'choices':list(f.choices or []) if hasattr(f,'choices') else []})
    result[model._meta.label]={'table':model._meta.db_table,'fields':fields,'constraints':[str(x) for x in model._meta.constraints]}
print(json.dumps({'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'server':'51.222.37.4','models':result},ensure_ascii=False,indent=2,default=str))
