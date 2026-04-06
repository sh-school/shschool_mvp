/**
 * tests/loadtest/k6_smoke.js
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━
 * k6 Smoke & Load Test — SchoolOS Production
 *
 * Tests public endpoints that don't require authentication:
 * - /health/  (DB + Redis check)
 * - /ready/   (DB only — readiness probe)
 * - /auth/login/ (login page load)
 *
 * Usage:
 *   k6 run tests/loadtest/k6_smoke.js
 *   k6 run --env BASE_URL=https://shschoolmvp-production.up.railway.app tests/loadtest/k6_smoke.js
 *
 * Stages:
 *   1. Ramp up to 20 users (30s)
 *   2. Hold 50 users (1m)
 *   3. Spike to 100 users (30s)
 *   4. Cool down (30s)
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

// ── Custom Metrics ──
const errorRate = new Rate("errors");
const healthLatency = new Trend("health_latency", true);
const loginPageLatency = new Trend("login_page_latency", true);

// ── Configuration ──
const BASE_URL = __ENV.BASE_URL || "https://shschoolmvp-production.up.railway.app";

export const options = {
  stages: [
    { duration: "30s", target: 20 },   // Warm up
    { duration: "1m", target: 50 },     // Normal load
    { duration: "30s", target: 100 },   // Spike
    { duration: "30s", target: 0 },     // Cool down
  ],
  thresholds: {
    http_req_duration: ["p(95)<2000"],   // 95% of requests < 2s
    http_req_failed: ["rate<0.05"],      // < 5% failure rate
    errors: ["rate<0.05"],               // Custom error rate < 5%
    health_latency: ["p(95)<500"],       // Health check < 500ms
  },
};

export default function () {
  // ── 1. Health Check (most critical) ──
  const healthRes = http.get(`${BASE_URL}/health/`, {
    tags: { name: "health" },
  });

  healthLatency.add(healthRes.timings.duration);

  const healthOk = check(healthRes, {
    "health: status 200": (r) => r.status === 200,
    "health: body contains ok": (r) => r.body && r.body.includes('"ok"'),
    "health: latency < 500ms": (r) => r.timings.duration < 500,
  });
  errorRate.add(!healthOk);

  sleep(0.5);

  // ── 2. Ready Check ──
  const readyRes = http.get(`${BASE_URL}/ready/`, {
    tags: { name: "ready" },
  });

  check(readyRes, {
    "ready: status 200": (r) => r.status === 200,
  });

  sleep(0.5);

  // ── 3. Login Page Load ──
  const loginRes = http.get(`${BASE_URL}/auth/login/`, {
    tags: { name: "login_page" },
    redirects: 5,
  });

  loginPageLatency.add(loginRes.timings.duration);

  const loginOk = check(loginRes, {
    "login: status 200 or 302": (r) => r.status === 200 || r.status === 302,
    "login: latency < 2s": (r) => r.timings.duration < 2000,
  });
  errorRate.add(!loginOk);

  sleep(Math.random() * 2 + 1); // 1-3s think time
}

export function handleSummary(data) {
  const now = new Date().toISOString().slice(0, 19).replace(/:/g, "-");
  return {
    stdout: textSummary(data, { indent: " ", enableColors: true }),
    [`tests/loadtest/results/k6-${now}.json`]: JSON.stringify(data, null, 2),
  };
}

function textSummary(data, opts) {
  // k6 built-in summary handles this
  return "";
}
