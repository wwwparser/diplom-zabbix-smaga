"""Run on bastion after Ansible: python3 scripts/configure_zabbix.py.
Creates hosts, actual USE items, graphs with threshold lines, and dashboard.
"""
import json, pathlib, urllib.request, time, yaml

ROOT=pathlib.Path(__file__).resolve().parents[1]
secrets=yaml.safe_load((ROOT/'ansible/secrets.yml').read_text())
token=None
def api(method,params):
    data={'jsonrpc':'2.0','method':method,'params':params,'id':1}
    if token: data['auth']=token
    req=urllib.request.Request('http://diplom-zabbix.ru-central1.internal/api_jsonrpc.php',data=json.dumps(data).encode(),headers={'Content-Type':'application/json-rpc'})
    reply=json.load(urllib.request.urlopen(req,timeout=30))
    if 'error' in reply: raise RuntimeError(json.dumps(reply['error']))
    return reply['result']

current_password=secrets['reviewer_password']
try: token=api('user.login',{'username':'Admin','password':secrets['reviewer_password']})
except Exception:
    current_password='zabbix'
    token=api('user.login',{'username':'Admin','password':current_password})
uid=api('user.get',{'filter':{'username':'Admin'}})[0]['userid']
if current_password != secrets['reviewer_password']:
    api('user.update',{'userid':uid,'passwd':secrets['reviewer_password'],'current_passwd':current_password})
token=None
token=api('user.login',{'username':'Admin','password':secrets['reviewer_password']})
groups=api('hostgroup.get',{'filter':{'name':'Diplom'}})
gid=groups[0]['groupid'] if groups else api('hostgroup.create',{'name':'Diplom'})['groupids'][0]
templates=api('template.get',{'filter':{'host':'Linux by Zabbix agent'}})
tid=templates[0]['templateid']
itemspec=[
 ('Disk I/O busy','diplom.disk.busy_ms',0,0,None,'%',80),
 ('Network softirq budget exhaustion','diplom.net.saturation',0,0,None,'events/s',0),
 ('Memory OOM errors','diplom.memory.errors',0,3,None,'',0),
 ('CPU utilization','diplom.cpu.util',15,0,'100-last(//system.cpu.util[,idle])','%',80),
 ('CPU queue per core','system.cpu.load[percpu,avg1]',0,0,None,'',1),
 ('RAM used','vm.memory.size[pused]',0,0,None,'%',90),
 ('Swap utilization','system.swap.size[,pused]',0,0,None,'%',20),
 ('Root disk utilization','vfs.fs.size[/,pused]',0,0,None,'%',80),
 ('Disk I/O queue','diplom.disk.queue',0,0,None,'',2),
 ('Network receive','diplom.net.in',0,3,None,'Bps',None),
 ('Network transmit','diplom.net.out',0,3,None,'Bps',None),
 ('Network errors','diplom.net.errors',0,3,None,'',0),
 ('Network dropped packets','diplom.net.drops',0,3,None,'',0),
 ('Failed systemd units','diplom.services.failed',0,3,None,'',0),
 ('Kernel hardware errors','diplom.kernel.errors',0,3,None,'',0),
 ('Memory allocation stalls','diplom.memory.stalls',0,3,None,'',0),
 ('Disk I/O errors','diplom.disk.errors',0,3,None,'',0),
]
pages=[]
for node in ['web-a','web-b','elastic','zabbix','kibana','bastion']:
    host='diplom-'+node+'.ru-central1.internal'
    found=api('host.get',{'filter':{'host':host}})
    if found: hid=found[0]['hostid']
    else:
        hid=api('host.create',{'host':host,'groups':[{'groupid':gid}],'templates':[{'templateid':tid}],'interfaces':[{'type':1,'main':1,'useip':0,'ip':'','dns':host,'port':'10050'}]})['hostids'][0]
    iface=api('hostinterface.get',{'hostids':[hid]})[0]['interfaceid']
    widgets=[]
    specs=itemspec + ([
        ('HTTP requests per second','diplom.http.requests',0,0,None,'req/s',None),
        ('HTTP active connections','diplom.http.active',0,3,None,'',100),
        ('HTTP 5xx per second','diplom.http.errors',0,0,None,'errors/s',0),
    ] if node.startswith('web-') else [])
    for i,(name,key,typ,value_type,params,units,threshold) in enumerate(specs):
        found=api('item.get',{'hostids':[hid],'filter':{'key_':key}})
        if found: itemid=found[0]['itemid']
        else:
            spec={'hostid':hid,'name':name,'key_':key,'type':typ,'value_type':value_type,'delay':'30s','history':'7d','trends':'30d','units':units}
            if typ==0: spec['interfaceid']=iface
            if params: spec['params']=params
            if key in ['diplom.net.in','diplom.net.out','diplom.http.requests','diplom.http.errors','diplom.net.saturation','diplom.disk.busy_ms']:
                spec['preprocessing']=[{'type':10,'params':'','error_handler':0,'error_handler_params':''}]
                spec['value_type']=0
                if key=='diplom.disk.busy_ms':
                    spec['preprocessing'].append({'type':1,'params':'0.1','error_handler':0,'error_handler_params':''})
            itemid=api('item.create',spec)['itemids'][0]
        gitems=[{'itemid':itemid,'color':'199C0D','sortorder':0}]
        if threshold is not None:
            tkey='diplom.threshold.'+key.replace('[','_').replace(']','_').replace(',','_').replace('/','_')
            existing=api('item.get',{'hostids':[hid],'filter':{'key_':tkey}})
            threshold_id=existing[0]['itemid'] if existing else api('item.create',{'hostid':hid,'name':name+' threshold','key_':tkey,'type':15,'value_type':0,'params':str(threshold),'delay':'30s'})['itemids'][0]
            gitems.append({'itemid':threshold_id,'color':'FF0000','sortorder':1})
            expr=f'avg(/{host}/{key},5m)>{threshold}' if threshold>0 else f'last(/{host}/{key})>0'
            desc=host+' '+name+' above threshold'
            if not api('trigger.get',{'filter':{'description':desc}}): api('trigger.create',{'description':desc,'expression':expr,'priority':3})
        gname='USE '+name
        graphs=api('graph.get',{'hostids':[hid],'filter':{'name':gname}})
        graphid=graphs[0]['graphid'] if graphs else api('graph.create',{'name':gname,'width':900,'height':200,'gitems':gitems})['graphids'][0]
        widgets.append({'type':'graph','name':name,'x':(i%2)*36,'y':(i//2)*5,'width':36,'height':5,'fields':[{'type':0,'name':'source_type','value':0},{'type':6,'name':'graphid','value':graphid}]})
    if node.startswith('web-'):
        scenario='HTTP / '+node
        if not api('httptest.get',{'hostids':[hid],'filter':{'name':scenario}}):
            api('httptest.create',{'hostid':hid,'name':scenario,'delay':'30s','steps':[{'name':'Root page','url':'http://'+host+'/','no':1,'required':'nginx','status_codes':'200'}]})
        for suffix,name in [('web.test.time['+scenario+',Root page,resp]','HTTP response time'),('web.test.fail['+scenario+']','HTTP failed steps')]:
            found=api('item.get',{'hostids':[hid],'webitems':True,'filter':{'key_':suffix}})
            if found:
                graphs=api('graph.get',{'hostids':[hid],'filter':{'name':name}})
                limit=1 if name=='HTTP response time' else 0
                limitkey='diplom.threshold.http.response' if limit else 'diplom.threshold.http.fail'
                limits=api('item.get',{'hostids':[hid],'filter':{'key_':limitkey}})
                limitid=limits[0]['itemid'] if limits else api('item.create',{'hostid':hid,'name':name+' threshold','key_':limitkey,'type':15,'value_type':0,'params':str(limit),'delay':'30s'})['itemids'][0]
                gitems=[{'itemid':found[0]['itemid'],'color':'2774A4','sortorder':0},{'itemid':limitid,'color':'FF0000','sortorder':1}]
                if graphs:
                    graphid=graphs[0]['graphid']
                    api('graph.update',{'graphid':graphid,'gitems':gitems})
                else: graphid=api('graph.create',{'name':name,'width':900,'height':200,'gitems':gitems})['graphids'][0]
                i=len(widgets)
                widgets.append({'type':'graph','name':name,'x':(i%2)*36,'y':(i//2)*5,'width':36,'height':5,'fields':[{'type':0,'name':'source_type','value':0},{'type':6,'name':'graphid','value':graphid}]})
    pages.append({'name':node,'widgets':widgets})
dash=api('dashboard.get',{'filter':{'name':'Diplom - USE infrastructure'}})
if dash: api('dashboard.update',{'dashboardid':dash[0]['dashboardid'],'pages':pages})
else: api('dashboard.create',{'name':'Diplom - USE infrastructure','pages':pages})
print(json.dumps({'hosts':api('host.get',{'groupids':[gid],'output':['hostid','host','status']}),'dashboard':api('dashboard.get',{'filter':{'name':'Diplom - USE infrastructure'}})},ensure_ascii=False,indent=2))
