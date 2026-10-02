#!/usr/bin/env bash
set -euo pipefail
cd ~/diplom
echo "Verification UTC: $(date -u +%FT%TZ)"
echo '=== Ansible Zabbix recap ==='
tail -n 4 zabbix-fix.log
tail -n 9 metrics-install.log
echo '=== Monitoring configuration ==='
cat zabbix-config-result.json
echo '=== Log collection ==='
curl -fsS 'http://diplom-elastic.ru-central1.internal:9200/nginx-*/_count'; echo
curl -fsS -H 'Content-Type: application/json' 'http://diplom-elastic.ru-central1.internal:9200/nginx-*/_search' -d '{"size":0,"aggs":{"nodes":{"terms":{"field":"node"}},"types":{"terms":{"field":"log_type"}}}}'; echo
echo '=== Identical web content ==='
for host in diplom-web-a.ru-central1.internal diplom-web-b.ru-central1.internal; do
 ssh -i ~/.ssh/diplom "$host" 'hostname; sha256sum /var/www/html/index.html; sudo docker ps --format "{{.Names}} {{.Status}}"'
done
