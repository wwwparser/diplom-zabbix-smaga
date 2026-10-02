"""Read actual item state/history and export monitoring evidence."""
import json, pathlib, urllib.request, yaml
root=pathlib.Path(__file__).resolve().parents[1]
password=yaml.safe_load((root/'ansible/secrets.yml').read_text())['reviewer_password']
token=None
def api(method,params):
    body={'jsonrpc':'2.0','method':method,'params':params,'id':1}
    if token: body['auth']=token
    request=urllib.request.Request('http://diplom-zabbix.ru-central1.internal/api_jsonrpc.php',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    result=json.load(urllib.request.urlopen(request,timeout=30))
    if 'error' in result: raise RuntimeError(result['error'])
    return result['result']
token=api('user.login',{'username':'Admin','password':password})
hosts=api('host.get',{'filter':{'host':['diplom-'+n+'.ru-central1.internal' for n in ['web-a','web-b','elastic','zabbix','kibana','bastion']]},'output':['hostid','host'],'selectInterfaces':['available','error']})
for host in hosts:
    items=api('item.get',{'hostids':[host['hostid']],'search':{'key_':'diplom.'},'output':['key_','name','state','error','lastvalue','lastclock']})
    host['custom_items']=items
    host['http_items']=api('item.get',{'hostids':[host['hostid']],'webitems':True,'search':{'key_':'web.test'},'output':['key_','name','state','error','lastvalue','lastclock']})
print(json.dumps(hosts,indent=2))
