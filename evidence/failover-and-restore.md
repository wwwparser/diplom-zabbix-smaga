# Протокол практических проверок

Проверки выполнены 2 октября 2026 года на действующих ВМ Яндекс Облака. Этот файл — краткая запись наблюдений, а не подмена полного stdout.

## Отказ nginx

Сценарий: `bash ~/diplom/test_failover.sh 158.160.166.202`. Начало — 06:58:39 UTC.

- До остановки: 12 ответов HTTP 200, в заголовках присутствуют оба backend `diplom-web-a` и `diplom-web-b`.
- `ansible diplom-web-a.ru-central1.internal -i ansible/inventory.ini -b -m service -a 'name=nginx state=stopped'`.
- После ожидания 20 секунд: 12 из 12 ответов HTTP 200, каждый `X-Backend: diplom-web-b`.
- После `state=started` и ожидания health check оба backend снова отвечают. nginx оставлен работающим.

Проверка не измеряет нулевое время переключения: запросы между остановкой и завершением 20-секундного ожидания в этой серии не отправлялись.

## Восстановление файла

Источник — плановый снимок web-b `fd8bc708schlqj49uarg`, созданный в 06:47 UTC, состояние READY. Временный диск создан через `yc compute disk create --source-snapshot-id ... --zone ru-central1-b`, подключён к web-b, раздел `/dev/vdb1` смонтирован `ro,noload`.

Фактический вывод:

```text
941dd9e74650dc279772573afee45c67eb5e2d079efdeb23b87d6bbc532ae83a  /var/www/html/index.html
941dd9e74650dc279772573afee45c67eb5e2d079efdeb23b87d6bbc532ae83a  /mnt/restore-check/var/www/html/index.html
TARGET             SOURCE    FSTYPE OPTIONS
/mnt/restore-check /dev/vdb1 ext4   ro,relatime,norecovery
```

Раздел размонтирован, временный диск отключён и удалён. Проверка подтверждает наличие и чтение файла в резервной копии. Полное восстановление PostgreSQL здесь не заявляется.
