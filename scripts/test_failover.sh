#!/usr/bin/env bash
set -euo pipefail
cd ~/diplom
ALB=${1:?Usage: test_failover.sh ALB_IP}
restore() { ansible diplom-web-a.ru-central1.internal -i ansible/inventory.ini -b -m service -a 'name=nginx state=started'; }
trap restore EXIT
echo "Start UTC: $(date -u +%FT%TZ)"
echo '=== Both backends ==='
for i in $(seq 1 12); do curl -fsS -D - -o /dev/null "http://$ALB/" | grep -iE 'HTTP/|X-Backend'; done
ansible diplom-web-a.ru-central1.internal -i ansible/inventory.ini -b -m service -a 'name=nginx state=stopped'
sleep 20
echo '=== One backend stopped, health check converged ==='
for i in $(seq 1 12); do curl -fsS -D - -o /dev/null "http://$ALB/" | grep -iE 'HTTP/|X-Backend'; done
ansible diplom-web-a.ru-central1.internal -i ansible/inventory.ini -b -m service -a 'name=nginx state=started'
sleep 20
echo '=== Both backends restored ==='
for i in $(seq 1 12); do curl -fsS -D - -o /dev/null "http://$ALB/" | grep -iE 'HTTP/|X-Backend'; done
echo "End UTC: $(date -u +%FT%TZ)"
