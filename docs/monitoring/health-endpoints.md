# Health Endpoints Documentation

SchoolOS exposes three health endpoints for monitoring, load balancing, and operational visibility.

## Endpoints Overview

| Endpoint   | Purpose                        | Auth Required | Response |
|------------|--------------------------------|---------------|----------|
| `/health/` | Liveness probe (DB + Redis)    | No            | JSON     |
| `/ready/`  | Readiness probe (DB only)      | No            | JSON     |
| `/status/` | Full system status dashboard   | No            | JSON     |

---

## GET /health/

**Purpose:** Liveness check for monitoring and alerting systems.

Checks database connectivity and Redis/cache availability.

**Response 200:**
```json
{
  "status": "ok",
  "version": "v5.4",
  "checks": {
    "db": "ok",
    "cache": "ok"
  },
  "latency_ms": 12.3
}
```

**Response 503 (degraded):**
```json
{
  "status": "degraded",
  "version": "v5.4",
  "checks": {
    "db": "ok",
    "cache": "error: ConnectionError"
  },
  "latency_ms": 5023.1
}
```

---

## GET /ready/

**Purpose:** Readiness probe for load balancers and Kubernetes rolling deployments.

Checks database only (lightweight). Returns 503 if the container is not ready to accept traffic.

**Response 200:**
```json
{
  "ready": true,
  "latency_ms": 2.1
}
```

**Response 503:**
```json
{
  "ready": false,
  "latency_ms": 5001.2
}
```

---

## GET /status/

**Purpose:** Full system status for operations dashboards and incident response.

Returns detailed information about all subsystems including latency, migration state, app version, and uptime.

**Response 200:**
```json
{
  "status": "healthy",
  "timestamp": "2026-04-06T12:30:00.000000+03:00",
  "version": "v5.4",
  "uptime_seconds": 86400.5,
  "checks": {
    "database": {
      "status": "connected",
      "latency_ms": 1.8
    },
    "redis": {
      "status": "connected",
      "latency_ms": 0.9
    },
    "migrations": {
      "all_applied": true
    }
  }
}
```

**Response 503 (unhealthy):**
```json
{
  "status": "unhealthy",
  "timestamp": "2026-04-06T12:30:00.000000+03:00",
  "version": "v5.4",
  "uptime_seconds": 120.3,
  "checks": {
    "database": {
      "status": "disconnected",
      "latency_ms": null
    },
    "redis": {
      "status": "connected",
      "latency_ms": 1.2
    },
    "migrations": {
      "all_applied": true
    }
  }
}
```

---

## Usage Recommendations

### Kubernetes / Railway
- **Liveness probe:** `/health/` with 30s interval, 5s timeout
- **Readiness probe:** `/ready/` with 10s interval, 3s timeout
- **Startup probe:** `/ready/` with 5s interval, 60s failure threshold

### Uptime Monitoring (UptimeRobot, Pingdom)
- Monitor `/health/` and alert on non-200 responses

### Operations Dashboard
- Poll `/status/` every 30-60 seconds for full system visibility
- Use `uptime_seconds` to detect unexpected restarts
- Use `migrations.all_applied` to verify post-deployment state

### SSL Exemption
All three endpoints are exempt from SSL redirect in production and staging settings to allow internal HTTP probes from load balancers and container orchestrators.
