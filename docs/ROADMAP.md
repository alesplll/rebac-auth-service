# План развития ReBAC Auth Service → интеграция с Open-S3

Цель: довести **rebac-auth-service** до production-ready состояния и использовать его как единственный сервис авторизации в проекте **open-s3** (собственный S3-совместимый хранилище).

---

## 1. Текущее состояние vs целевая архитектура

| Компонент | Сейчас | Цель (твой план + open-s3) |
|-----------|--------|-----------------------------|
| **Граф** | Узлы: User, Group, Resource. Рёбра: MEMBER_OF, OWNER_OF, VIEWER, HAS_PERMISSION. Транзитивность реализована | ✅ Готово |
| **gRPC** | Check, WriteTuple, DeleteTuple, Read | ✅ Контракт стабилен для S3 |
| **Redis** | Кэш решений, TTL 30s. Инвалидация через SCAN+DEL по паттерну | ✅ Готово |
| **Kafka** | Events: tuple_written, tuple_deleted, ACCESS_GRANTED/ACCESS_DENIED | ✅ Готово |
| **Observability** | gRPC Health check (стандартный протокол) | Prometheus + Grafana → в open-s3 (OTel) |
| **Deploy** | Dockerfile, docker-compose (infra + app profile), CI/CD (GitHub Actions) | K8s/Helm → в open-s3 |
| **Open-S3** | — | S3 API вызывает `Check(subject, action, object)` по gRPC |

---

## 2. Схема графа (Graph Schema) — унификация под S3 и твой план

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
| `HAS_PERMISSION` | Group → Resource | Прямые права группы на ресурс. Свойство `level`: "read" \| "write" \| "delete" \| "admin" |
| `OWNER_OF` / `VIEWER` | User/Group → Resource | Legacy; выдают полные или read права |
| `PARENT_OF` | Resource → Resource | Иерархия: bucket → prefix/folder → object |

### 2.3 Действия (Actions) для open-s3

Маппинг S3 API → action для `Check(subject, action, object)`:

| S3 операция | action | object (пример) |
|-------------|--------|------------------|
| GetObject | `read` | `object:bucket/key` |
| PutObject | `write` | `object:bucket/key` |
| DeleteObject | `delete` | `object:bucket/key` |
| ListBucket | `read` | `bucket:bucket-name` |
| CreateBucket | `admin` | `bucket:bucket-name` |
| DeleteBucket | `admin` | `bucket:bucket-name` |

---

## 3. Логика проверки (Core Logic) — транзитивность ✅

Реализовано в `internal/neo4j/store.py`. Два пути:

1. **Transitive HAS_PERMISSION** — `(subject)-[:MEMBER_OF*0..]->(x)-[:HAS_PERMISSION {level}]->(resource)`. Маппинг `level → action` в `schema.py:ALLOWED_LEVELS_PER_ACTION`.
2. **Legacy direct relations** — OWNER_OF/VIEWER через `schema.py:PERMISSION_RULES`.

---

## 4. gRPC API — контракт для open-s3 ✅

- `Check(subject, action, object)` → `{allowed, reason}`
- `WriteTuple(subject, relation, object, level?)` → `{success}`
- `DeleteTuple(subject, relation, object)` → `{success}`
- `Read(subject)` → `{tuples[]}`
- `Health` (стандартный gRPC health protocol, используется K8s liveness/readiness)

В open-s3:
- subject = `user:<id>` (из IAM/OIDC)
- action = `read` / `write` / `delete` / `admin`
- object = `bucket:name` или `object:bucket/key`

---

## 5. Redis — кэш и инвалидация ✅

- Ключ: `auth_decision:{subject}:{action}:{object}`
- TTL: 30 сек
- При WriteTuple/DeleteTuple → Kafka событие → consumer делает SCAN+DEL по паттерну `auth_decision:*:*:{object_id}`

---

## 6. Kafka — аудит и инвалидация ✅

- Топик `auth-changes`: `tuple_written` / `tuple_deleted` (с subject_id, object_id для инвалидации)
- Топик `audit-logs`: `ACCESS_GRANTED` / `ACCESS_DENIED` (subject, action, object, timestamp)

---

## 7. Observability — в контексте open-s3

Standalone Prometheus/Grafana для одного сервиса избыточен.
Метрики и трейсинг будут добавлены в **open-s3** через **OpenTelemetry**:
- OTel SDK в rebac-auth-service (instrumentation для gRPC + custom counters)
- Экспорт в OTel Collector → Prometheus/Tempo/Loki в open-s3
- Grafana дашборд на уровне open-s3

gRPC Health (уже реализован) покрывает K8s liveness/readiness.

---

## 8. Docker & Deploy

### Реализовано ✅
- `Dockerfile` — multi-stage, Python 3.12
- `deploy/local/docker-compose.yml` — инфраструктура (Neo4j, Redis, Kafka, Zookeeper) + сам сервис через profile `app`
- CI/CD: GitHub Actions (unit tests + integration tests с Neo4j)

### Конфигурация через env vars
| Переменная | Default (local) | В Docker/K8s |
|---|---|---|
| `NEO4J_URI` | `bolt://localhost:7687` | `bolt://neo4j:7687` |
| `NEO4J_USER` | `neo4j` | из Secret |
| `NEO4J_PASSWORD` | `password123` | из Secret |
| `REDIS_HOST` | `localhost` | `redis` |
| `REDIS_PORT` | `6379` | `6379` |
| `KAFKA_BOOTSTRAP` | `localhost:9092` | `kafka:29092` |
| `GRPC_PORT` | `50051` | `50051` |

### Запуск
```bash
# Только инфраструктура (для локальной разработки):
docker compose -f deploy/local/docker-compose.yml up -d

# Инфраструктура + сервис (полный стек):
docker compose -f deploy/local/docker-compose.yml --profile app up -d
```

### K8s/Helm → в open-s3
Deployment, Service, ConfigMap, Secret, Ingress будут частью open-s3 инфраструктуры.

---

## 9. Open-S3 — как будет использоваться этот сервис

В проекте open-s3 (отдельный репозиторий):

- На каждый входящий S3-запрос (GetObject, PutObject, DeleteObject, ListBucket, CreateBucket, DeleteBucket и т.д.):
  - Извлечь идентификатор пользователя (из подписи запроса, IAM, OIDC).
  - Сформировать subject (например `user:<id>`), action по таблице из п. 2.3, object (`bucket:name` или `object:bucket/key`).
  - Вызвать gRPC `Check(subject, action, object)` в rebac-auth-service.
  - При `allowed=false` вернуть клиенту 403 Forbidden.
  - При `allowed=true` выполнить операцию с хранилищем.

Требования к rebac-auth-service со стороны open-s3:
- Стабильный proto (subject, action, object — строки) ✅
- Низкая задержка (кэш Redis, цель <10 ms в норме) ✅
- gRPC Health для K8s probes ✅
- Dockerfile для включения в docker-compose / K8s ✅

---

## 10. Итог чек-лист

- [x] Схема графа: User, Group, Resource; MEMBER_OF*0.., HAS_PERMISSION (level); PARENT_OF
- [x] Neo4j: Cypher с транзитивностью (User→Group*→Resource + legacy OWNER_OF/VIEWER)
- [x] gRPC: Check, WriteTuple, DeleteTuple, Read
- [x] Redis: инвалидация по паттерну (SCAN+DEL)
- [x] Kafka: аудит решений (ACCESS_GRANTED/ACCESS_DENIED) + инвалидация
- [x] gRPC Health check (стандартный протокол, K8s liveness/readiness)
- [x] Dockerfile (multi-stage, Python 3.12) + .dockerignore
- [x] docker-compose (инфра + `--profile app` для полного стека)
- [x] CI/CD: GitHub Actions (unit + integration tests)
- [ ] OTel instrumentation → делается в open-s3
- [ ] K8s/Helm манифесты → делается в open-s3
- [ ] open-s3: вызов Check(subject, action, object) перед каждой S3-операцией
