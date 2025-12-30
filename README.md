<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/gRPC-Enabled-00C7B7?logo=google-cloud&logoColor=white" alt="gRPC" />
  <img src="https://img.shields.io/badge/Neo4j-Graph%20DB-008CC1?logo=neo4j&logoColor=white" alt="Neo4j" />
  <img src="https://img.shields.io/badge/Redis-Cache-DC382D?logo=redis&logoColor=white" alt="Redis" />
  <img src="https://img.shields.io/badge/Kafka-Event%20Stream-231F20?logo=apache-kafka&logoColor=white" alt="Kafka" />
  <img src="https://img.shields.io/badge/Docker-Containerized-2496ED?logo=docker&logoColor=white" alt="Docker" />
  <img src="https://img.shields.io/badge/Kubernetes-Orchestrated-326CE5?logo=kubernetes&logoColor=white" alt="Kubernetes" />
  <img src="https://img.shields.io/badge/Prometheus-Metrics-E6522C?logo=prometheus&logoColor=white" alt="Prometheus" />
  <img src="https://img.shields.io/badge/Grafana-Dashboards-F46800?logo=grafana&logoColor=white" alt="Grafana" />
  <img src="https://img.shields.io/badge/Loki-Logs-5A30B5?logo=grafana&logoColor=white" alt="Loki" />
  <img src="https://img.shields.io/badge/Sentry-Errors-362D59?logo=sentry&logoColor=white" alt="Sentry" />
</p>

<p align="center">
  <strong>ReBAC Auth Service</strong> · Relationship-Based Authorization Engine 🔐
</p>

---

# ReBAC Auth Service 🔐

ReBAC Auth Service is a centralized **relationship-based access control (ReBAC)** engine exposed via a clean **gRPC API** for permission checks.  
Instead of hard-coding role checks in every microservice, other services ask this service questions like:

> “Can user <code>alice</code> <strong>read</strong> resource <code>doc:123</code>?” ✅

All access rules are stored as a **graph** of users, groups, and resources, and authorization decisions are made by traversing this graph.

---

## ✨ Core Idea

Traditional RBAC assigns permissions to roles and then maps users to those roles. ReBAC uses **relationships** between entities to derive access, which is more natural for complex, real-world systems.  

Example relationships:

- 👤 `alice` **MEMBER_OF** `team:payments`
- 🧑‍💻 `team:payments` **OWNER_OF** `folder:billing`
- 📄 `doc:invoice-42` **IN** `folder:billing`

Even without an explicit “allow read” on the document, `alice` may still be allowed to read it because of this chain.

---

## 🧩 Features

- 🔗 **gRPC API** for:
  - Writing relationships (tuples) between subjects and objects.
  - Reading relationships for debugging/tools.
  - Checking permissions (`Check(subject, action, object)`).
- 🕸️ **Graph-based ReBAC model** stored in a graph database.
- ⚡ **Redis cache** for low-latency decisions.
- 📡 **Kafka audit stream** for security and compliance.
- 📊 **Prometheus + Grafana** for metrics and dashboards.
- 📜 **Loki** for centralized logs.
- 🚨 **Sentry** for error tracking.
- 🐳 **Docker** images and ☸️ **Kubernetes** deployment manifests.
- 🔁 **CI/CD pipeline** for build, test, and deploy.

---

## 🏗️ Architecture Overview

High-level components:

- `rebac-auth-service` — gRPC authorization engine.
- Graph DB (e.g. Neo4j) — stores relationships and policies as a graph.
- Redis — cache for authorization decisions.
- Kafka — audit/event stream.
- Prometheus / Grafana / Loki / Sentry — observability stack.
- Docker + Kubernetes — packaging and orchestration.
- CI/CD — automated delivery pipeline.

---

## 🧠 Responsibility by Technology

### 🔐 gRPC ReBAC Service

- Defines the `.proto` contract.
- Implements:
  - `Check` — authorization decision.
  - `WriteTuple` — add/remove relationships.
  - `Read` — inspect relationships.
- Talks to:
  - Graph DB for relationship traversal.
  - Redis for caching.
  - Kafka for emitting audit events.

### 🕸️ Graph Database (Neo4j / other)

- Stores:
  - Nodes: `User`, `Group`, `Folder`, `Document`, `Project`, …
  - Edges: `MEMBER_OF`, `OWNER_OF`, `PARENT_OF`, `CAN_READ`, `CAN_EDIT`, …
- Resolves access via graph queries like:
  > “Is there an allowed path from subject to object for this action?”

### ⚡ Redis Cache

- Key: `check:{subject}:{action}:{object}`
- Value: `allow` / `deny`
- Short TTL to balance freshness and performance.
- Reduces load on the graph DB for hot paths and repeated checks.

### 📡 Kafka Audit Stream

- Receives events such as:
  - `TupleWritten` (changes to relationships).
  - Optionally `DecisionLogged` (authorization decisions with context).
- Enables:
  - Security analytics.
  - Forensics.
  - Possible future offline policy checks.

### 📊 Prometheus & Grafana

- Exported metrics examples:
  - `auth_check_requests_total`
  - `auth_check_latency_seconds` (p50, p95, p99)
  - `auth_cache_hits_total` / `auth_cache_misses_total`
  - Graph DB query duration
- Grafana dashboards to visualize service health over time.

### 📜 Loki (Logs)

- Aggregates logs from all containers:
  - gRPC requests (sanitized).
  - DB/cache interactions.
  - Internal warnings/errors.
- Queried from Grafana alongside metrics.

### 🚨 Sentry (Error Tracking)

- Captures exceptions and stack traces.
- Sends alerts when something goes wrong (e.g. DB connection errors, unexpected request shapes).

### 🐳 Docker & ☸️ Kubernetes

- Docker:
  - Packages service and dependencies into images.
  - Supports local dev via `docker-compose`.
- Kubernetes:
  - Deployments for stateless components (auth service, consumers).
  - StatefulSets (or equivalent) for Neo4j, Redis, Kafka.
  - Services for internal networking.
  - Probes for health checks and rolling updates.

### 🔁 CI/CD

- On each commit:
  1. Run tests & linters.
  2. Build Docker images.
  3. Push images to registry.
  4. Apply Kubernetes manifests / Helm charts for deployment.

---

## 🚀 Typical Flow

1. Client service calls `Check(user=alice, action="read", object="doc:invoice-42")` over gRPC.
2. Auth service:
   - Tries Redis cache.
   - On miss, queries the graph DB, computes the decision, writes back to cache.
   - Emits an audit event to Kafka.
3. Client receives `ALLOW` or `DENY` and continues its own business logic accordingly.

