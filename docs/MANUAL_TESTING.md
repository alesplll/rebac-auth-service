# Ручное тестирование ReBAC Auth Service (Arch Linux + venv)

Пошаговая последовательность: окружение → venv → инфраструктура → сервер → gRPC-запросы → просмотр графа в Neo4j.

---

## Шаг 0. Что должно быть установлено

- **Docker** и **Docker Compose** (для Neo4j/Redis/Kafka)
- **Python 3.12** (например, `pacman -S python`)
- **grpcurl** (например, `yay -S grpcurl` или скачать с GitHub)

---

## Шаг 1. Клонировать/перейти в проект и создать venv

Выполняй **строго из корня репозитория**:

```bash
cd /путь/к/rebac-auth-service

# Создать venv один раз
python -m venv venv

# Активировать venv (каждый новый терминал)
source venv/bin/activate
```

Должна появиться приставка `(venv)` в промпте. Все следующие команды — **в активированном venv**, если не сказано иначе.

---

## Шаг 2. Установить зависимости и сгенерировать gRPC-стабы

```bash
# Всё ещё из корня проекта, venv активирован
pip install -e .
pip install grpcio-tools

# Генерация стабов из proto
bash proto/generate.sh
```

Проверка: должны появиться файлы `internal/gen/authz_pb2.py` и `authz_pb2_grpc.py`.

---

## Шаг 3. Поднять инфраструктуру (Docker)

В **отдельном терминале** (venv не обязателен для Docker):

```bash
cd /путь/к/rebac-auth-service/deploy/local
docker compose up -d
```

Дождись запуска контейнеров. Проверка:

- **Neo4j**: в браузере открыть http://localhost:7474 — логин `neo4j`, пароль `password123`.
- **Redis**: `redis-cli ping` → ответ `PONG` (если redis-cli установлен).

---

## Шаг 4. Запустить gRPC-сервер

В терминале **с активированным venv**, из **корня проекта**:

```bash
source venv/bin/activate   # если ещё не активирован
cd /путь/к/rebac-auth-service

python -m entrypoints.server.main
```

В логах должно быть что-то вроде: `ReBAC Auth Service gRPC :50051` или `Neo4j ReBAC (transitive + HAS_PERMISSION)`. Сервер должен работать, не закрывай этот терминал.

---

## Шаг 5. gRPC-запросы (в том же порядке)

Все команды ниже — из **другого терминала** (сервер продолжает работать в первом). grpcurl вызывай с хоста (не из Docker), на Arch можно ставить так: `yay -S grpcurl` или бинарник с GitHub.

### 5.1 Убедиться, что сервис отвечает (reflection)

```bash
grpcurl -plaintext localhost:50051 list
```

Должен появиться список сервисов, в нём `rebac.authz.v1.PermissionService`.

---

### 5.2 Добавить связи (WriteTuple) — выполни по порядку

**Запрос 1.** Пользователь `alex` в группе `devops`:

```bash
grpcurl -plaintext -d '{"subject":"user:alex","relation":"MEMBER_OF","object":"group:devops"}' \
  localhost:50051 rebac.authz.v1.PermissionService/WriteTuple
```

Ожидаемый ответ: `{"success": true}`

**Запрос 2.** Группа `devops` имеет право уровня `admin` на ресурс `server-1`:

```bash
grpcurl -plaintext -d '{"subject":"group:devops","relation":"HAS_PERMISSION","object":"resource:server-1","level":"admin"}' \
  localhost:50051 rebac.authz.v1.PermissionService/WriteTuple
```

Ожидаемый ответ: `{"success": true}`

**Запрос 3.** Группа `viewers` имеет право только `read` на ресурс `doc1`:

```bash
grpcurl -plaintext -d '{"subject":"group:viewers","relation":"HAS_PERMISSION","object":"resource:doc1","level":"read"}' \
  localhost:50051 rebac.authz.v1.PermissionService/WriteTuple
```

**Запрос 4.** Пользователь `bob` в группе `viewers`:

```bash
grpcurl -plaintext -d '{"subject":"user:bob","relation":"MEMBER_OF","object":"group:viewers"}' \
  localhost:50051 rebac.authz.v1.PermissionService/WriteTuple
```

**Запрос 5–7.** Цепочка для транзитивности: alice → payments → finance → billing:

```bash
grpcurl -plaintext -d '{"subject":"user:alice","relation":"MEMBER_OF","object":"group:payments"}' \
  localhost:50051 rebac.authz.v1.PermissionService/WriteTuple

grpcurl -plaintext -d '{"subject":"group:payments","relation":"MEMBER_OF","object":"group:finance"}' \
  localhost:50051 rebac.authz.v1.PermissionService/WriteTuple

grpcurl -plaintext -d '{"subject":"group:finance","relation":"HAS_PERMISSION","object":"resource:billing","level":"read"}' \
  localhost:50051 rebac.authz.v1.PermissionService/WriteTuple
```

---

### 5.3 Проверки доступа (Check)

**Alex может admin и read на server-1 (через группу devops):**

```bash
grpcurl -plaintext -d '{"subject":"user:alex","action":"admin","object":"resource:server-1"}' \
  localhost:50051 rebac.authz.v1.PermissionService/Check
# Ожидаем: {"allowed": true, ...}

grpcurl -plaintext -d '{"subject":"user:alex","action":"read","object":"resource:server-1"}' \
  localhost:50051 rebac.authz.v1.PermissionService/Check
# Ожидаем: {"allowed": true}
```

**Eve без прав — отказ:**

```bash
grpcurl -plaintext -d '{"subject":"user:eve","action":"read","object":"resource:server-1"}' \
  localhost:50051 rebac.authz.v1.PermissionService/Check
# Ожидаем: {"allowed": false}
```

**Bob может read, но не write на doc1:**

```bash
grpcurl -plaintext -d '{"subject":"user:bob","action":"read","object":"resource:doc1"}' \
  localhost:50051 rebac.authz.v1.PermissionService/Check
# Ожидаем: {"allowed": true}

grpcurl -plaintext -d '{"subject":"user:bob","action":"write","object":"resource:doc1"}' \
  localhost:50051 rebac.authz.v1.PermissionService/Check
# Ожидаем: {"allowed": false}
```

**Alice может read на billing по цепочке (транзитивность), но не write:**

```bash
grpcurl -plaintext -d '{"subject":"user:alice","action":"read","object":"resource:billing"}' \
  localhost:50051 rebac.authz.v1.PermissionService/Check
# Ожидаем: {"allowed": true}

grpcurl -plaintext -d '{"subject":"user:alice","action":"write","object":"resource:billing"}' \
  localhost:50051 rebac.authz.v1.PermissionService/Check
# Ожидаем: {"allowed": false}
```

---

### 5.4 Чтение связей (Read)

```bash
# Все исходящие связи user:alex
grpcurl -plaintext -d '{"subject":"user:alex"}' \
  localhost:50051 rebac.authz.v1.PermissionService/Read

# Все исходящие связи group:devops (должна быть HAS_PERMISSION с level)
grpcurl -plaintext -d '{"subject":"group:devops"}' \
  localhost:50051 rebac.authz.v1.PermissionService/Read
```

---

## Шаг 6. Как посмотреть весь граф связей в Neo4j

1. Открой **Neo4j Browser**: http://localhost:7474  
2. Войди: логин `neo4j`, пароль `password123`.  
3. В поле ввода (вверху) выполни по очереди запросы на языке **Cypher**.

### Показать все узлы и все связи (весь граф)

```cypher
MATCH (n)-[r]->(m)
RETURN n, r, m
```

Отобразится граф: узлы (User, Group, Resource) и рёбра (MEMBER_OF, HAS_PERMISSION с level).

### Только узлы и типы связей (таблицей)

```cypher
MATCH (a)-[r]->(b)
RETURN a.id AS from, type(r) AS relation, b.id AS to
```

Для HAS_PERMISSION можно вывести и уровень:

```cypher
MATCH (a)-[r:HAS_PERMISSION]->(b)
RETURN a.id AS subject, r.level AS level, b.id AS object
```

### Все узлы по типам

```cypher
MATCH (n) RETURN labels(n)[0] AS type, n.id AS id
```

### Очистить граф (если нужно начать с нуля)

```cypher
MATCH (n) DETACH DELETE n
```

После этого заново выполни блок **5.2** (WriteTuple), чтобы снова построить граф.

---

## Шаг 7. Запуск тестов (в venv, из корня проекта)

```bash
source venv/bin/activate
cd /путь/к/rebac-auth-service
```

**Только юнит-тесты** (Neo4j/Redis не нужны):

```bash
pytest tests/unit -v
```

**Интеграционные тесты** (должны быть подняты Neo4j и сервис, см. шаги 3–4):

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_PASSWORD=password123
pytest tests/integration -v -m integration
```

---

## Краткая последовательность (чек-лист)

| # | Действие |
|---|----------|
| 1 | `cd` в проект → `python -m venv venv` → `source venv/bin/activate` |
| 2 | `pip install -e .` → `pip install grpcio-tools` → `bash proto/generate.sh` |
| 3 | В другом терминале: `cd deploy/local` → `docker compose up -d` |
| 4 | В терминале с venv: `python -m entrypoints.server.main` (оставить запущенным) |
| 5 | В третьем терминале: выполнить gRPC-запросы из раздела 5 (сначала WriteTuple, потом Check, потом Read) |
| 6 | В браузере http://localhost:7474 → Cypher: `MATCH (n)-[r]->(m) RETURN n, r, m` чтобы увидеть весь граф |
