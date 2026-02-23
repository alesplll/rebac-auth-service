# План развития ReBAC Auth Service → интеграция с Open-S3

Цель: довести **rebac-auth-service** до production-ready состояния и использовать его как единственный сервис авторизации в проекте **open-s3** (собственный S3-совместимый хранилище).

---

## 1. Текущее состояние vs целевая архитектура

| Компонент | Сейчас | Цель (твой план + open-s3) |
|-----------|--------|-----------------------------|
| **Граф** | Узлы: User, Group, Document, Folder, Resource. Рёбра: MEMBER_OF, OWNER_OF, VIEWER, PARENT_OF. Проверка только **прямая** связь subject→object | Транзитивность: путь User→Group*→Resource. Опционально: HAS_PERMISSION {level}. Иерархия ресурсов (bucket/folder→object) |
| **gRPC** | Check, WriteTuple, Read | Check + AddRelation + RemoveRelation (или DeleteTuple). Контракт стабилен для S3 |
| **Redis** | Кэш решений, TTL 30s. Инвалидация по Kafka (есть баг: Redis `delete` не по паттерну) | Исправить инвалидацию (SCAN+DEL по паттерну или отдельные ключи в событии). Цель: <10 ms, cache hit rate >80% |
| **Kafka** | События tuple_written + invalidation_hints | + аудит ACCESS_DENIED / ACCESS_GRANTED для безопасности и аналитики |
| **Observability** | Нет | Prometheus метрики (P99, cache hit rate, Neo4j latency), Grafana дашборд |
| **Deploy** | Нет | Docker, docker-compose, K8s/Helm, CI/CD (тесты → образ → деплой) |
| **Open-S3** | — | S3 API (GetObject, PutObject, DeleteObject, ListBucket, CreateBucket) перед каждым действием вызывает `Check(subject, action, object)` по gRPC |

---

## 2. Схема графа (Graph Schema) — унификация под S3 и твой план

Привести модель к одному виду, удобному и для общего ReBAC, и для S3.

### 2.1 Узлы (Nodes)

| Label | id (пример) | Назначение |
|-------|-------------|------------|
| `User` | `user:alice`, `user:123` | Пользователь (в S3 — от IAM/OIDC) |
| `Group` | `group:developers`, `group:admins` | Группа для транзитивных прав |
| `Resource` | `bucket:my-bucket`, `object:my-bucket/path/to/file` | Ресурс (в S3: bucket или object key). Атрибут `type`: "bucket" \| "object" |

Имеет смысл оставить также `Folder` как алиас/подтип Resource для иерархии (папка = префикс в S3), либо кодировать всё в `Resource` с иерархией через PARENT_OF.

### 2.2 Рёбра (Relations)

| Relation | От → К | Смысл |
|----------|--------|--------|
| `MEMBER_OF` | User → Group (или Group → Group для вложенности) | Принадлежность; транзитивность по группам |
| `HAS_PERMISSION` | Group → Resource | Прямые права группы на ресурс. Опционально свойство `level`: "read" \| "write" \| "delete" \| "admin" |
| `OWNER_OF` / `VIEWER` | User/Group → Resource | Можно оставить как есть или свести к HAS_PERMISSION {level} |
| `PARENT_OF` | Resource → Resource | Иерархия: bucket → prefix/folder → object (для наследования прав по пути) |

Твой вариант с `HAS_PERMISSION {level}` хорошо ложится на S3-действия: read→GetObject/ListBucket, write→PutObject/DeleteObject, admin→CreateBucket/DeleteBucket/ACL.

### 2.3 Действия (Actions) для open-s3

Маппинг S3 API → action для `Check(subject, action, object)`:

| S3 операция | action | object (пример) |
|-------------|--------|------------------|
| GetObject | `read` или `s3:GetObject` | `object:bucket/key` |
| PutObject | `write` или `s3:PutObject` | `object:bucket/key` |
| DeleteObject | `delete` | `object:bucket/key` |
| ListBucket | `read` или `s3:ListBucket` | `bucket:bucket-name` |
| CreateBucket | `admin` или `s3:CreateBucket` | (ресурс можно глобальный или не передавать) |
| DeleteBucket | `admin` или `s3:DeleteBucket` | `bucket:bucket-name` |

В proto можно оставить `action` строкой и в S3-шлюзе подставлять эти значения.

---

## 3. Логика проверки (Core Logic) — транзитивность

Сейчас в `Neo4jStore.check()` проверяется только прямая связь:

```cypher
MATCH (subject {id: $subject})-[rel]->(target {id: $object})
WHERE type(rel) IN $allowed_rels
```

Нужно заменить на поиск **пути** с транзитивностью по группам и опционально по иерархии ресурсов.

### 3.1 Вариант 1: только группы (как в твоём плане)

```cypher
MATCH (u:User {id: $subject})
  -[:MEMBER_OF*0..]->(g:Group)
  -[:HAS_PERMISSION|OWNER_OF|VIEWER]->(r:Resource {id: $object})
WHERE ...
RETURN count(r) > 0 AS authorized
```

`*0..` — ноль или больше шагов MEMBER_OF (User сам считается "группой глубины 0", либо явно группы).

### 3.2 Вариант 2: иерархия ресурсов (права на папку = права на объект внутри)

Если объект `object:bucket/path/to/file`, а права выданы на `object:bucket/path` или `bucket:bucket`:

```cypher
MATCH (u:User {id: $subject})-[:MEMBER_OF*0..]->(g:Group)-[perm]->(res:Resource)
WHERE res.id = $object
   OR ($object STARTS WITH res.id + "/" OR res.id = $object)
...
```

Или хранить явные PARENT_OF и идти вверх по дереву. Выбор — между простотой (только прямой ресурс) и гибкостью (наследование по пути).

План работ:

- В `internal/neo4j/schema.py`: зафиксировать PERMISSION_RULES под HAS_PERMISSION/OWNER_OF/VIEWER и действия read/write/delete/admin.
- В `internal/neo4j/store.py`: реализовать новый Cypher с путём User→Group*→Resource (и при желании с учётом PARENT_OF). Оставить старый запрос под флагом или заменить сразу.

---

## 4. gRPC API — контракт для open-s3

Текущий контракт уже подходит: `Check(subject, action, object)`. Для админки и консистентности кэша полезно добавить явное удаление связи.

### 4.1 Оставить как есть (минимальные изменения)

- `Check` — без изменений (поля уже subject/action/object).
- `WriteTuple` — использовать как AddRelation.
- `Read` — для отладки и админки.

Дополнительно (по желанию):

- `RemoveRelation` / `DeleteTuple(subject, relation, object)` — удаление одного кортежа; при событии в Kafka инвалидировать кэш так же, как при добавлении.

### 4.2 Именование под open-s3

В proto можно оставить общие имена (subject, action, object). В open-s3 при вызове:

- subject = идентификатор из твоего IAM/OIDC (например `user:alice` или `user:123`).
- action = `read` / `write` / `delete` / `admin` (или детальные `s3:GetObject` и т.д.).
- object = `bucket:name` или `object:bucket/key`.

Отдельный proto-файл для S3 не обязателен — достаточно соглашения об формате subject/action/object.

---

## 5. Redis — кэш и инвалидация (Cache Consistency)

- Ключ: как сейчас `auth_decision:{subject}:{action}:{object}` (или с префиксом из конфига).
- TTL: 30–60 сек; под нагрузкой подобрать по P99 и hit rate (цель >80%).
- При AddRelation/RemoveRelation (WriteTuple/DeleteTuple) — публикуем событие в Kafka с подсказками инвалидации.

Важно: в текущем коде инвалидация по «паттерну» через `redis.delete(pattern)` неверна — Redis `DELETE` не принимает wildcards. Нужно:

- Либо в событии передавать список **конкретных ключей** к инвалидации (например, все ключи, где object = изменённый ресурс, перечислены в событии),
- Либо consumer по паттерну делает `SCAN` + `DEL` по ключам (медленнее, но гибко).

Рекомендация: в событии из producer передавать `object_id` (и опционально subject_id); consumer по известному префиксу ключа и списку subject/action/object из конфига или из другого топика не нужен — проще генерировать ключи по правилу «все решения, где object = X» и держать в Redis набор ключей по ресурсу (или один «tag» ключ по ресурсу, по которому при инвалидации делаем SCAN). Либо хранить в Kafka полный набор ключей для инвалидации. Самый простой вариант: в consumer по событию делать SCAN по паттерну `auth_decision:*:*:*:object_id` и удалять найденные ключи.

План:

- Исправить инвалидацию в `internal/cache/invalidation_consumer.py` (SCAN+DEL по паттерну или явный список ключей в событии).
- В `internal/cache/redis_cache.py` при необходимости добавить метод `invalidate_by_object(object_id)` для консьюмера.

---

## 6. Kafka — аудит и инвалидация

- Топик `auth-changes`: уже есть; события при WriteTuple (и при RemoveRelation/DeleteTuple).
- Расширить события: добавлять в сообщение object_id, subject_id, event_type (tuple_added / tuple_removed).
- Отдельный топик или тот же: при каждом Check (или только при DENY) слать событие для аудита:
  - `event_type`: `ACCESS_GRANTED` | `ACCESS_DENIED`
  - subject, action, object, timestamp, (опционально) request_id.

План:

- В `PermissionService.check()` после определения allowed вызывать audit_producer.send_decision_event(subject, action, object, allowed).
- В producer добавить метод `send_decision_event(...)` и отправку в топик `audit-logs` (или второй топик по выбору).
- Consumer для аналитики (ClickHouse/файл/Loki) — отдельная задача (можно позже).

---

## 7. Observability — Prometheus & Grafana

- Метрики (Prometheus):
  - `auth_check_requests_total` (counter, labels: result=allow|deny).
  - `auth_check_duration_seconds` (histogram) — цель P99 < 50 ms.
  - `auth_cache_hits_total`, `auth_cache_misses_total` (или один counter с label hit/miss).
  - `neo4j_query_duration_seconds` (histogram) для запроса check.
- Экспорт через `prometheus_client` в Python; эндпоинт `/metrics` на отдельном HTTP-порту (или рядом с gRPC, если добавить HTTP-сервер в тот же процесс).
- Grafana: дашборд с графиками P99, cache hit rate, RPS, ошибок.

План:

- Добавить зависимость `prometheus_client`.
- В `cmd/server/main.py` поднять HTTP-сервер (e.g. port 9090) с `/metrics`.
- В `PermissionService`/`Neo4jStore`/`RedisDecisionCache` инжектировать счётчики и гистограммы, обновлять их при каждом Check и при обращении к кэшу/Neo4j.

---

## 8. Docker, Kubernetes, CI/CD

- Dockerfile: multi-stage, Python 3.12, только runtime-зависимости; точка входа — запуск gRPC-сервера (и при необходимости cache-invalidator отдельным образом).
- docker-compose.yml: rebac-auth-service, Neo4j, Redis, Kafka (+ Zookeeper при необходимости); удобно для локальной разработки и прогона транзитивного Check.
- Kubernetes:
  - Deployment для rebac-auth-service (и отдельно для cache-invalidator).
  - Сервисы для Neo4j, Redis, Kafka (или Helm-чарты).
  - ConfigMap/Secret для URI, паролей, bootstrap Kafka.
  - Probes: liveness/readiness по gRPC health или HTTP `/health`.
- CI/CD (GitLab CI или GitHub Actions):
  - На каждый пуш: линтер, тесты.
  - Сборка Docker-образа, push в registry.
  - (Опционально) деплой в Minikube/тестовый кластер по тегу или ветке.

План:

- Добавить Dockerfile, .dockerignore.
- Добавить docker-compose.yml (сервис + Neo4j + Redis + Kafka).
- Добавить манифесты k8s/ или Helm chart (deployment, service, config).
- Добавить пайплайн (e.g. `.gitlab-ci.yml` или `.github/workflows`).

---

## 9. Open-S3 — как будет использоваться этот сервис

В проекте open-s3 (отдельный репозиторий):

- На каждый входящий S3-запрос (GetObject, PutObject, DeleteObject, ListBucket, CreateBucket, DeleteBucket и т.д.):
  - Извлечь идентификатор пользователя (из подписи запроса, IAM, OIDC).
  - Сформировать subject (например `user:<id>`), action по таблице из п. 2.3, object (`bucket:name` или `object:bucket/key`).
  - Вызвать gRPC `Check(subject, action, object)` в rebac-auth-service.
  - При `allowed=false` вернуть клиенту 403 Forbidden.
  - При `allowed=true` выполнить операцию с хранилищем (файловая система или другой бэкенд).

Требования к rebac-auth-service со стороны open-s3:

- Стабильный proto (subject, action, object — строки).
- Низкая задержка (кэш Redis, цель <10 ms в норме).
- Доступность по сети (в K8s — Service, в dev — localhost:50051).

Отдельно в open-s3 нужно будет:

- Настройка создания пользователей/групп и выдача прав (через WriteTuple/AddRelation) — админ-API или скрипты, которые дергают rebac-auth-service.

---

## 10. Roadmap по неделям (как не забросить)

Учитывая, что база уже есть (gRPC, Neo4j, Redis, Kafka, инвалидация), план смещён в сторону «дотянуть логику и инфраструктуру».

| Неделя | Фокус | Задачи |
|--------|--------|--------|
| **1** | Граф и транзитивность | 1) Обновить схему (HAS_PERMISSION, level). 2) Реализовать в Neo4j запрос с путём User→Group*→Resource. 3) Юнит/интеграционные тесты на типовых графах (Alex→DevOps→Server-1). |
| **2** | API и кэш | 1) Добавить DeleteTuple/RemoveRelation в proto и в сервис. 2) Исправить инвалидацию Redis (SCAN+DEL или список ключей в Kafka). 3) Аудит ACCESS_DENIED/ACCESS_GRANTED в Kafka. |
| **3** | Observability и стабильность | 1) Prometheus метрики + HTTP /metrics. 2) Grafana дашборд (P99, cache hit rate, Neo4j latency). 3) Health check для K8s. |
| **4** | DevOps и open-s3 | 1) Dockerfile + docker-compose. 2) K8s/Helm (deployment, services, config). 3) CI: тесты + сборка образа. 4) В open-s3: первый вызов gRPC Check перед одной операцией (например GetObject). |

Дальше:

- Полная интеграция open-s3 со всеми операциями (Get/Put/Delete/List/CreateBucket/DeleteBucket).
- По необходимости: наследование прав по иерархии ресурсов (PARENT_OF), более тонкие действия (s3:GetObject, s3:PutObject) в схеме.

---

## 11. Итог чек-лист

- [ ] Схема графа: User, Group, Resource; MEMBER_OF*0.., HAS_PERMISSION (level); опционально PARENT_OF.
- [ ] Neo4j: Cypher с путём (транзитивность), замена текущей прямой проверки.
- [ ] gRPC: DeleteTuple/RemoveRelation + инвалидация кэша при удалении.
- [ ] Redis: инвалидация по паттерну (SCAN+DEL) или по списку ключей в событии.
- [ ] Kafka: аудит решений (ACCESS_GRANTED/ACCESS_DENIED).
- [ ] Prometheus + Grafana: метрики и дашборд, цель P99 < 50 ms, hit rate > 80%.
- [ ] Docker + docker-compose + K8s/Helm + CI (тесты, образ, деплой).
- [ ] open-s3: вызов Check(subject, action, object) перед каждой S3-операцией; маппинг S3→action и object_id.

После этого у тебя будет один репозиторий (rebac-auth-service), готовый к использованию в open-s3 и демонстрирующий архитектуру ReBAC с графом, кэшем, аудитом и наблюдаемостью.
