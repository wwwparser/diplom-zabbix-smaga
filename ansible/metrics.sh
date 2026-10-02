#!/bin/bash
# Counters read from the kernel, never fabricated. Zabbix preprocessing turns
# cumulative network/request counters into per-second rates where required.
case "$1" in
 net.in) awk -F '[: ]+' 'NR>2 && $2!="lo" {n+=$3} END{print n+0}' /proc/net/dev ;;
 net.out) awk -F '[: ]+' 'NR>2 && $2!="lo" {n+=$11} END{print n+0}' /proc/net/dev ;;
 net.errors) awk -F '[: ]+' 'NR>2 && $2!="lo" {n+=$5+$13} END{print n+0}' /proc/net/dev ;;
 net.drops) awk -F '[: ]+' 'NR>2 && $2!="lo" {n+=$6+$14} END{print n+0}' /proc/net/dev ;;
 disk.queue) awk '$3=="vda" {print $12}' /proc/diskstats ;;
 disk.busy_ms) awk '$3=="vda" {print $13}' /proc/diskstats ;;
 net.saturation) n=0; while read -r processed dropped squeezed rest; do n=$((n+16#$squeezed)); done </proc/net/softnet_stat; echo "$n" ;;
 memory.errors) journalctl -k --no-pager --since '-5 minutes' 2>/dev/null | grep -icE 'out of memory|oom-kill|killed process' || true ;;
 memory.stalls) awk '/^allocstall/ {n+=$2} END{print n+0}' /proc/vmstat ;;
 services.failed) systemctl --failed --no-legend --plain | wc -l ;;
 kernel.errors) journalctl -k --no-pager --since '-5 minutes' 2>/dev/null | grep -icE 'hardware error|machine check|mce:' || true ;;
 disk.errors) journalctl -k --no-pager --since '-5 minutes' 2>/dev/null | grep -icE 'I/O error|blk_update_request.*error' || true ;;
 http.requests) curl -sf http://127.0.0.1/nginx_status | awk 'NR==3 {print $3}' ;;
 http.active) curl -sf http://127.0.0.1/nginx_status | awk 'NR==1 {print $3}' ;;
 http.errors) awk '$9 ~ /^5[0-9][0-9]$/ {n++} END {print n+0}' /var/log/nginx/access.log ;;
esac
