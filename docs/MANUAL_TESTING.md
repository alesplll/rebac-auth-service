# Ручное тестирование ReBAC Auth Service

Как поднять окружение и проверить работу сервиса вручную (gRPC, транзитивность, уровни доступа).

---

## 1. Поднять инфраструктуру (Neo4j, Redis, Kafka)

Из корня проекта:

```bash
cd deploy/local
docker compose up -d
```

Проверка Neo4j: открой в браузере http://localhost:7474 (логин `neo4j`, пароль `password123`).

Проверка Redis: `redis-cli ping` → `PONG`.

---

## 2. Сгенерировать gRPC-стабы и установить зависимости

```bash
# из корня проекта
bash proto/generate.sh
pip install -e .
# или с venv:
# ./venv/bin/pip install -e .
# ./venv/bin/python -m grpc_tools.protoc ... (см. proto/generate.sh)
```

---

## 3. Запустить gRPC-сервер

```bash
python -m entrypoints.server.main
# или после pip install -e .:
rebac-server
```

В логе должно быть: `ReBAC Auth Service gRPC :50051`.

---

## 4. Проверки через grpcurl

Установи [grpcurl](https://github.com/fullstorydev/grpcurl) (или используй другой gRPC-клиент).

### 4.1 Добавить связи (WriteTuple)

Пользователь `alex` в группе `devops`, группа `devops` имеет право `admin` на ресурс `server-1`:

```bash
# user:alex MEMBER_OF group:devops
grpcurl -plaintext -d '{"subject":"user:alex","relation":"MEMBER_OF","object":"group:devops"}' \
  localhost:50051 rebac.authz.v1.PermissionService/WriteTuple

# group:devops HAS_PERMISSION (level=admin) -> resource:server-1
grpcurl -plaintext -d '{"subject":"group:devops","relation":"HAS_PERMISSION","object":"resource:server-1","level":"admin"}' \
  localhost:50051 rebac.authz.v1.PermissionService/WriteTuple
```

Ожидаемый ответ в обоих случаях: `{"success": true}`.

### 4.2 Проверка доступа (Check) — транзитивность

Alex должен получить доступ к server-1 через группу devops:

```bash
# Проверка: может ли user:alex выполнить action "admin" над resource:server-1
grpcurl -plaintext -d '{"subject":"user:alex","action":"admin","object":"resource:server-1"}' \
  localhost:50051 rebac.authz.v1.PermissionService/Check
# Ожидаем: {"allowed": true, "reason": "..."}

# read тоже разрешён (admin включает read)
grpcurl -plaintext -d '{"subject":"user:alex","action":"read","object":"resource:server-1"}' \
  localhost:50051 rebac.authz.v1.PermissionService/Check
# Ожидаем: {"allowed": true}
```

Пользователь без прав:

```bash
grpcurl -plaintext -d '{"subject":"user:eve","action":"read","object":"resource:server-1"}' \
  localhost:50051 rebac.authz.v1.PermissionService/Check
# Ожидаем: {"allowed": false}
```

### 4.3 Чтение связей (Read)

```bash
grpcurl -plaintext -d '{"subject":"user:alex"}' \
  localhost:50051 rebac.authz.v1.PermissionService/Read
# Должна быть хотя бы одна связь: user:alex MEMBER_OF group:devops

grpcurl -plaintext -d '{"subject":"group:devops"}' \
  localhost:50051 rebac.authz.v1.PermissionService/Read
# Должна быть связь с level: group:devops HAS_PERMISSION(admin) resource:server-1
```

### 4.4 Уровни доступа: read / write / create / delete / admin

Добавь группу с правом только `read` на ресурс и проверь:

```bash
# group:viewers HAS_PERMISSION read -> resource:doc1
grpcurl -plaintext -d '{"subject":"group:viewers","relation":"HAS_PERMISSION","object":"resource:doc1","level":"read"}' \
  localhost:50051 rebac.authz.v1.PermissionService/WriteTuple

# user:bob MEMBER_OF group:viewers
grpcurl -plaintext -d '{"subject":"user:bob","relation":"MEMBER_OF","object":"group:viewers"}' \
  localhost:50051 rebac.authz.v1.PermissionService/WriteTuple

# bob может read
grpcurl -plaintext -d '{"subject":"user:bob","action":"read","object":"resource:doc1"}' \
  localhost:50051 rebac.authz.v1.PermissionService/Check
# {"allowed": true}

# bob не может write
grpcurl -plaintext -d '{"subject":"user:bob","action":"write","object":"resource:doc1"}' \
  localhost:50051 rebac.authz.v1.PermissionService/Check
# {"allowed": false}
```

---

## 5. Запуск тестов

**Только юнит-тесты** (без Neo4j/Redis/Kafka):

```bash
pytest tests/unit -v
```

**Интеграционные тесты** (нужен запущенный Neo4j, например через `deploy/local/docker-compose`):

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_PASSWORD=password123
pytest tests/integration -v -m integration
```

Все тесты (юнит + интеграция; интеграция пропустится, если Neo4j недоступен):

```bash
pytest tests -v
```

---

## 6. Цепочка групп (транзитивность)

Проверка сценария: Alice → group:payments → group:finance → resource:billing (read).

В Neo4j Browser (http://localhost:7474) или через grpcurl:

```bash
grpcurl -plaintext -d '{"subject":"user:alice","relation":"MEMBER_OF","object":"group:payments"}' \
  localhost:50051 rebac.authz.v1.PermissionService/WriteTuple
grpcurl -plaintext -d '{"subject":"group:payments","relation":"MEMBER_OF","object":"group:finance"}' \
  localhost:50051 rebac.authz.v1.PermissionService/WriteTuple
grpcurl -plaintext -d '{"subject":"group:finance","relation":"HAS_PERMISSION","object":"resource:billing","level":"read"}' \
  localhost:50051 rebac.authz.v1.PermissionService/WriteTuple

# Проверка
grpcurl -plaintext -d '{"subject":"user:alice","action":"read","object":"resource:billing"}' \
  localhost:50051 rebac.authz.v1.PermissionService/Check
# Ожидаем: {"allowed": true}

grpcurl -plaintext -d '{"subject":"user:alice","action":"write","object":"resource:billing"}' \
  localhost:50051 rebac.authz.v1.PermissionService/Check
# Ожидаем: {"allowed": false}
```

---

## 7. Список методов (reflection)

Если на сервере включена gRPC reflection:

```bash
grpcurl -plaintext localhost:50051 list
grpcurl -plaintext localhost:50051 describe rebac.authz.v1.PermissionService
```

Так можно убедиться, что контракт и методы доступны.
