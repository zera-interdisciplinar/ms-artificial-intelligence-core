"""Five-minute conversation load against POST /api/v1/multi-agent/process-message.

Samples active users from ms-administrative-core Postgres (`user_account`:
id + unit_id). Each user keeps one thread and waits between turns, so the
100 users are not fired at once. In-flight calls are capped.

Flows, one per turn, rotated per user:
  faq, inventory, predict, report

Reads script/.env.qa when present (gitignored): QA database name/user and
the Kong apikey. Users are read with kubectl exec on deploy/postgres in
namespace qa (the Service is not exposed outside the cluster).

Env (same names as the admin-core service):
  DB_NAME, DB_USER, DB_NAMESPACE (default qa)
  BASE_URL (default https://www.zeratech.online/qa/ai-core — Kong QA, strip-path)
  APIKEY  Kong key-auth header (route /qa/ai-core exige api-key-auth)
  Each user gets an RS256 access token (iss=ms-administrative-core-qa, exp,
  role, email) signed with the QA private key from secret
  ms-administrative-core-jwt. Kong jwt-auth rejects an unsigned bearer with 401.
  TOKENS_JSON  optional {user_id: bearer_jwt} overrides the signed token.
  USERS=100  DURATION_SECONDS=300  MAX_IN_FLIGHT=5
  THINK_MIN=12  THINK_MAX=35
"""

import asyncio
import base64
import hashlib
import json
import os
import random
import statistics
import subprocess
import time
from uuid import uuid4

import httpx
import jwt
from cryptography.hazmat.primitives import serialization

_ENV_FILE = os.path.join(os.path.dirname(__file__), ".env.qa")


def _load_env_file() -> None:
    if not os.path.isfile(_ENV_FILE):
        return
    with open(_ENV_FILE, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key, value)


_load_env_file()

FLOWS = {
    "faq": "O que é o projeto Zera?",
    "inventory": "Qual o status atual do notebook de patrimônio NB-4521?",
    "predict": (
        "Qual a estimativa de tempo até falha de um notebook Dell Latitude 5420, "
        "fabricado em 2022, adquirido em 2023-01-15, em zona climática tropical, "
        "uso intenso (nível 8)?"
    ),
    "report": "Gere um relatório com o histórico de previsões de falha dos meus equipamentos.",
}
FLOW_NAMES = list(FLOWS)


_ISSUER = "ms-administrative-core-qa"


def _pem(secret: str, key: str) -> bytes:
    raw = subprocess.check_output(
        ["kubectl", "get", "secret", secret, "-n", os.environ.get("DB_NAMESPACE", "qa"), "-o", f"jsonpath={{.data.{key}}}"],
        text=True,
    )
    return base64.b64decode(raw)


def _signing_key() -> tuple[bytes, str]:
    """QA RSA private key and the kid admin-core puts on access tokens (SHA-256 prefix of the public key)."""
    private_pem = _pem("ms-administrative-core-jwt", "private\\.pem")
    public = serialization.load_pem_public_key(_pem("ms-administrative-core-jwt", "public\\.pem"))
    der = public.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    kid = hashlib.sha256(der).hexdigest()[:16]
    return private_pem, kid


def _bearer(user: dict, private_pem: bytes, kid: str) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "iss": _ISSUER,
            "iat": now,
            "exp": now + 3600,
            "sub": user["user_id"],
            "email": user["email"],
            "role": user["role"],
        },
        private_pem,
        algorithm="RS256",
        headers={"kid": kid},
    )


def _sample_users(limit: int) -> list[dict]:
    """Random ACTIVE rows from admin-core user_account (id, unit_id).

    QA Postgres is only reachable inside the cluster. kubectl exec into the
    postgres deployment uses the in-pod psql; DB_* still select the database.
    """
    env = os.environ.copy()
    password = env.get("DB_PASSWORD")
    if password:
        env["PGPASSWORD"] = password
    sql = (
        "SELECT id::text, unit_id::text, email, role FROM user_account "
        "WHERE status = 'ACTIVE' AND unit_id IS NOT NULL "
        f"ORDER BY random() LIMIT {int(limit)}"
    )
    completed = subprocess.run(
        [
            "kubectl", "exec", "-n", env.get("DB_NAMESPACE", "qa"),
            "deploy/postgres", "--",
            "psql",
            "-U", env.get("DB_USER", "admin_core"),
            "-d", env.get("DB_NAME", "admin_core"),
            "-tA", "-F", "\t", "-c", sql,
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(completed.stderr.strip() or "psql failed")
    users = []
    for line in completed.stdout.splitlines():
        user_id, unit_id, email, role = line.split("\t")
        if user_id and unit_id:
            users.append({"user_id": user_id, "unit_id": unit_id, "email": email, "role": role})
    if not users:
        raise SystemExit("no ACTIVE user_account with unit_id")
    return users


def _tokens() -> dict[str, str]:
    path = os.environ.get("TOKENS_JSON")
    if not path:
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


async def _turn(client: httpx.AsyncClient, sem: asyncio.Semaphore, user: dict, flow: str, thread_id: str, token: str) -> dict:
    body = {"thread_id": thread_id, "unit_id": user["unit_id"], "content": FLOWS[flow]}
    started = time.perf_counter()
    async with sem:
        try:
            headers = {"Authorization": f"Bearer {token}"}
            apikey = os.environ.get("APIKEY")
            if apikey:
                headers["apikey"] = apikey
            response = await client.post(
                "/api/v1/multi-agent/process-message",
                json=body,
                headers=headers,
            )
            latency = time.perf_counter() - started
            payload = response.json() if response.status_code == 200 else {}
            return {
                "flow": flow,
                "status": response.status_code,
                "latency_s": round(latency, 3),
                "blocked": payload.get("blocked"),
                "agent_trace": payload.get("agent_trace"),
                "error": None if response.status_code == 200 else response.text[:200],
            }
        except httpx.HTTPError as exc:
            return {"flow": flow, "status": 0, "error": str(exc), "latency_s": round(time.perf_counter() - started, 3), "blocked": None}


async def _user_loop(client, sem, user, token, deadline: float, think: tuple[float, float], results: list) -> None:
    thread_id = str(uuid4())
    step = random.randrange(len(FLOW_NAMES))
    await asyncio.sleep(random.uniform(0, think[1]))
    while time.perf_counter() < deadline:
        flow = FLOW_NAMES[step % len(FLOW_NAMES)]
        step += 1
        results.append(await _turn(client, sem, user, flow, thread_id, token))
        pause = random.uniform(*think)
        if time.perf_counter() + pause >= deadline:
            return
        await asyncio.sleep(pause)


def _summary(results: list[dict], users: int, elapsed: float) -> dict:
    latencies = [r["latency_s"] for r in results if r["status"] == 200]
    latencies.sort()

    def pct(p: float) -> float | None:
        if not latencies:
            return None
        return latencies[min(len(latencies) - 1, int(p * (len(latencies) - 1)))]

    by_flow: dict[str, int] = {}
    errors = 0
    for row in results:
        by_flow[row["flow"]] = by_flow.get(row["flow"], 0) + 1
        if row["status"] != 200:
            errors += 1
    return {
        "users": users,
        "elapsed_s": round(elapsed, 1),
        "turns": len(results),
        "error_rate": round(errors / len(results), 4) if results else None,
        "latency_p50_s": pct(0.50),
        "latency_p95_s": pct(0.95),
        "latency_mean_s": round(statistics.fmean(latencies), 3) if latencies else None,
        "turns_by_flow": by_flow,
        "blocked": sum(1 for r in results if r.get("blocked")),
    }


async def main() -> None:
    limit = int(os.environ.get("USERS", "100"))
    duration = float(os.environ.get("DURATION_SECONDS", "300"))
    users = _sample_users(limit)
    tokens = _tokens()
    private_pem, kid = _signing_key()
    base = os.environ.get("BASE_URL", "https://www.zeratech.online/qa/ai-core")
    if not os.environ.get("APIKEY"):
        print("APIKEY ausente: o Kong de QA rejeita /qa/ai-core sem o header apikey")
    sem = asyncio.Semaphore(int(os.environ.get("MAX_IN_FLIGHT", "5")))
    think = (float(os.environ.get("THINK_MIN", "12")), float(os.environ.get("THINK_MAX", "35")))
    results: list[dict] = []
    started = time.perf_counter()
    deadline = started + duration
    timeout = httpx.Timeout(180.0, connect=10.0)
    async with httpx.AsyncClient(base_url=base, timeout=timeout) as client:
        await asyncio.gather(
            *[
                _user_loop(client, sem, user, tokens.get(user["user_id"], _bearer(user, private_pem, kid)), deadline, think, results)
                for user in users
            ]
        )
    summary = _summary(results, len(users), time.perf_counter() - started)
    print(json.dumps({"summary": summary, "turns": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
