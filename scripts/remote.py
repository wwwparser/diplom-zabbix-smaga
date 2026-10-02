"""Local operator helper. Credentials remain local; gateway only forwards SSH.

Uses existing user-owned SSH gateway because direct routing to the new cloud IP
pool is unavailable from this workstation. No software is installed on gateway.
"""
import argparse, json, pathlib, sys
import paramiko
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

ROOT = pathlib.Path(__file__).resolve().parents[1]

def connect():
    cfg = json.loads((pathlib.Path.home()/'.claude.json').read_text(encoding='utf-8'))
    args = cfg['mcpServers']['ssh-mcp-my-server']['args']
    def arg(flag):
        return next(a.split('=',1)[1] for a in args if a.startswith(flag+'='))
    gateway = paramiko.SSHClient()
    gateway.load_system_host_keys()
    gateway.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    gateway.connect(arg('--host'), port=int(arg('--port')), username=arg('--user'), password=arg('--password'), timeout=15)
    ip = json.loads((ROOT/'.private/outputs.json').read_text(encoding='utf-8-sig'))['machines']['value']['bastion']['public_ip']
    channel = gateway.get_transport().open_channel('direct-tcpip', (ip,22), ('127.0.0.1',0), timeout=15)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(ip, username='ubuntu', key_filename=str(pathlib.Path.home()/'.ssh/id_ed25519'), sock=channel, timeout=15)
    return client, gateway

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('command', nargs='?', default='hostname; echo "$SSH_CONNECTION"')
    parser.add_argument('--upload', nargs=2)
    parser.add_argument('--script')
    parser.add_argument('--bootstrap-keys', action='store_true')
    options=parser.parse_args()
    client,gateway=connect()
    try:
        if options.bootstrap_keys:
            _,out,err=client.exec_command('cat ~/.ssh/diplom.pub')
            pub=out.read().decode().strip()
            if not pub.startswith('ssh-ed25519 '): raise RuntimeError('Missing deployment key')
            for name in ['web-a','web-b','elastic','zabbix','kibana','bastion']:
                channel=client.get_transport().open_channel('direct-tcpip',(f'diplom-{name}.ru-central1.internal',22),('127.0.0.1',0))
                host=paramiko.SSHClient();host.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                host.connect(f'diplom-{name}.ru-central1.internal',username='ubuntu',key_filename=str(pathlib.Path.home()/'.ssh/id_ed25519'),sock=channel)
                _,o,e=host.exec_command("printf '%s\\n' '"+pub+"' >> ~/.ssh/authorized_keys")
                if o.channel.recv_exit_status(): raise RuntimeError(e.read().decode())
                host.close();print(name+': deployment public key installed')
        elif options.upload:
            with client.open_sftp() as sftp: sftp.put(*options.upload)
        else:
            command=pathlib.Path(options.script).read_text(encoding='utf-8') if options.script else options.command
            _,out,err=client.exec_command(command,timeout=1800)
            for line in out: print(line,end='',flush=True)
            sys.stderr.write(err.read().decode())
            sys.exit(out.channel.recv_exit_status())
    finally:
        client.close();gateway.close()
