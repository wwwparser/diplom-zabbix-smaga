"""Local-only tunnels to real cloud UIs; no page content is substituted."""
import select, socketserver, threading, pathlib, yaml, base64
from remote import connect

client, gateway = connect()
password=yaml.safe_load((pathlib.Path(__file__).resolve().parents[1]/'ansible/secrets.yml').read_text())['reviewer_password']
authorization=base64.b64encode(('reviewer:'+password).encode())
targets = {18080: ('diplom-zabbix.ru-central1.internal', 80),
           15601: ('diplom-kibana.ru-central1.internal', 5601),
           18081: ('158.160.166.202', 80)}

class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        channel = client.get_transport().open_channel(
            'direct-tcpip', targets[self.server.server_address[1]], self.client_address)
        try:
            first=True
            while True:
                ready, _, _ = select.select([self.request, channel], [], [], 30)
                for source in ready:
                    data = source.recv(65536)
                    if not data: return
                    if source is self.request and data.startswith((b'GET ',b'POST ',b'PUT ',b'DELETE ',b'HEAD ')) and self.server.server_address[1]==15601:
                        line, rest=data.split(b'\r\n',1)
                        data=line+b'\r\nAuthorization: Basic '+authorization+b'\r\n'+rest
                    if source is self.request: first=False
                    (channel if source is self.request else self.request).sendall(data)
        finally: channel.close()

for port in targets:
    server = socketserver.ThreadingTCPServer(('127.0.0.1', port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
print('Cloud UI tunnels listening on localhost: 18080, 15601, 18081', flush=True)
threading.Event().wait()
