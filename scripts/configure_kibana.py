"""Create real nginx data view and a saved Discover search."""
import base64,json,pathlib,urllib.request,yaml
root=pathlib.Path(__file__).resolve().parents[1]
password=yaml.safe_load((root/'ansible/secrets.yml').read_text())['reviewer_password']
auth=base64.b64encode(('reviewer:'+password).encode()).decode()
def api(path,body=None,method=None):
    request=urllib.request.Request('http://diplom-kibana.ru-central1.internal:5601'+path,
        data=json.dumps(body).encode() if body is not None else None,method=method,
        headers={'Authorization':'Basic '+auth,'kbn-xsrf':'diplom','Content-Type':'application/json'})
    return json.load(urllib.request.urlopen(request,timeout=60))
view=api('/api/data_views/data_view',{'data_view':{'id':'diplom-nginx','title':'nginx-*','name':'Diplom nginx access and error','timeFieldName':'@timestamp'},'override':True})
api('/api/data_views/default',{'data_view_id':'diplom-nginx','force':True})
search={'attributes':{'title':'Diplom - nginx logs from both nodes','description':'Real Filebeat nginx access/error logs','columns':['node','log_type','message'],'sort':[['@timestamp','desc']],'kibanaSavedObjectMeta':{'searchSourceJSON':json.dumps({'indexRefName':'kibanaSavedObjectMeta.searchSourceJSON.index','query':{'query':'','language':'kuery'},'filter':[]})}},'references':[{'name':'kibanaSavedObjectMeta.searchSourceJSON.index','type':'index-pattern','id':'diplom-nginx'}]}
api('/api/saved_objects/search/diplom-nginx-logs?overwrite=true',search)
print(json.dumps({'data_view_id':view['data_view']['id'],'search_id':'diplom-nginx-logs'},indent=2))
