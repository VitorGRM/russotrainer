"""Sessões interrompíveis: salvar, retomar e mapear o progresso pergunta a pergunta.

Uma sessão é a fila de telas que o aluno está percorrendo (uma unidade, uma
parte de lição de vocabulário, um prefixo, um jogo de terminações…). O cliente
envia a fila compacta depois de cada resposta e a cada mudança de tela; o
servidor guarda em ``session_state``. Para retomar, a fila é reconstruída a
partir dos IDs, na mesma ordem e com as alternativas na mesma posição, sem o
gabarito. Cada resposta continua gravada em ``attempts`` como sempre: a sessão
guarda só *onde o aluno parou* e o que ele já viu, não as notas.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import Callable


SESSION_KINDS = {"study", "vocab", "prefix", "morph", "lesson"}
KEY_PATTERN = re.compile(r"^[A-Za-z0-9_:.\-]{3,140}$")
MAX_QUEUE = 400
STATUS_VALUES = {"new", "correct", "partial", "wrong", "pending", "seen", "retry"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS session_state (
    key TEXT PRIMARY KEY,
    course_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    resume_index INTEGER NOT NULL DEFAULT 0,
    total INTEGER NOT NULL DEFAULT 0,
    answered INTEGER NOT NULL DEFAULT 0,
    elapsed_ms INTEGER NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_session_state_active
    ON session_state(course_id, status, updated_at);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _int(value: object, low: int, high: int) -> int:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return low
    return max(low, min(high, number))


def clean_save_payload(data: dict) -> dict:
    """Valida e compacta o que o cliente enviou; levanta ValueError se inválido."""
    key = str(data.get("key") or "")
    if not KEY_PATTERN.match(key):
        raise ValueError("Chave de sessão inválida.")
    kind = str(data.get("kind") or "")
    if kind not in SESSION_KINDS:
        raise ValueError("Tipo de sessão desconhecido.")
    queue_in = data.get("queue")
    if not isinstance(queue_in, list) or not queue_in:
        raise ValueError("Fila vazia.")
    if len(queue_in) > MAX_QUEUE:
        raise ValueError("Fila grande demais.")

    queue: list[dict] = []
    for entry in queue_in:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            raise ValueError("Entrada de fila inválida.")
        item: dict = {"id": entry["id"][:80]}
        options = entry.get("options")
        if isinstance(options, list) and options and all(isinstance(option, str) for option in options):
            item["options"] = options[:12]
        if entry.get("retry"):
            item["retry"] = True
        if entry.get("fmt") == "input":
            item["fmt"] = "input"
        queue.append(item)

    status_in = data.get("status") if isinstance(data.get("status"), list) else []
    status = [value if value in STATUS_VALUES else "new" for value in status_in[: len(queue)]]
    status += ["new"] * (len(queue) - len(status))

    results: list[dict] = []
    for result in (data.get("results") if isinstance(data.get("results"), list) else [])[:MAX_QUEUE * 3]:
        if not isinstance(result, dict):
            continue
        results.append({
            "exercise_id": str(result.get("exercise_id", ""))[:80],
            "is_correct": result.get("is_correct") if result.get("is_correct") in (True, False, None) else None,
            "is_partial": bool(result.get("is_partial")),
            "score": result.get("score") if isinstance(result.get("score"), (int, float)) else None,
            "retry": bool(result.get("retry")),
            "prompt": str(result.get("prompt", ""))[:300],
            "correct_answer": str(result.get("correct_answer") or "")[:300],
        })

    meta_in = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    meta = {
        name: (value if isinstance(value, (str, int, float, bool, dict)) or value is None else str(value))
        for name, value in meta_in.items()
        if isinstance(name, str) and len(name) < 40
    }
    retries = meta.get("retries")
    if isinstance(retries, dict):
        meta["retries"] = {
            str(name)[:80]: _int(count, 0, 5) for name, count in list(retries.items())[:MAX_QUEUE]
        }

    return {
        "key": key,
        "kind": kind,
        "course_id": str(data.get("course_id") or "russian")[:20],
        "title": str(data.get("title") or key)[:200],
        "resume_index": _int(data.get("resume_index"), 0, len(queue)),
        "total": len(queue),
        "answered": _int(data.get("answered"), 0, MAX_QUEUE * 3),
        "elapsed_ms": _int(data.get("elapsed_ms"), 0, 10**10),
        "payload": {"queue": queue, "status": status, "results": results, "meta": meta},
    }


class SessionStore:
    def __init__(self, connect: Callable[[], sqlite3.Connection], lock: threading.Lock):
        self._connect = connect
        self._lock = lock

    @staticmethod
    def init_schema(conn: sqlite3.Connection) -> None:
        conn.executescript(SCHEMA)

    def save(self, data: dict) -> dict:
        clean = clean_save_payload(data)
        now = _now()
        with self._lock, self._connect() as conn:
            existing = conn.execute(
                "SELECT created_at FROM session_state WHERE key = ?", (clean["key"],)
            ).fetchone()
            created = existing["created_at"] if existing else now
            conn.execute(
                """
                INSERT INTO session_state (
                    key, course_id, kind, title, status, resume_index, total,
                    answered, elapsed_ms, payload_json, created_at, updated_at, completed_at
                ) VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, NULL)
                ON CONFLICT(key) DO UPDATE SET
                    course_id=excluded.course_id, kind=excluded.kind, title=excluded.title,
                    status='active', resume_index=excluded.resume_index, total=excluded.total,
                    answered=excluded.answered, elapsed_ms=excluded.elapsed_ms,
                    payload_json=excluded.payload_json, updated_at=excluded.updated_at,
                    completed_at=NULL
                """,
                (
                    clean["key"], clean["course_id"], clean["kind"], clean["title"],
                    clean["resume_index"], clean["total"], clean["answered"], clean["elapsed_ms"],
                    json.dumps(clean["payload"], ensure_ascii=False), created, now,
                ),
            )
            conn.commit()
        return {"key": clean["key"], "updated_at": now, "resume_index": clean["resume_index"], "total": clean["total"]}

    def active(self, course_id: str = "") -> list[dict]:
        sql = (
            "SELECT key, course_id, kind, title, resume_index, total, answered, elapsed_ms, "
            "created_at, updated_at FROM session_state WHERE status = 'active'"
        )
        args: list[str] = []
        if course_id:
            sql += " AND course_id = ?"
            args.append(course_id)
        sql += " ORDER BY updated_at DESC"
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(sql, args)]

    def row(self, key: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM session_state WHERE key = ? AND status = 'active'", (key,)
            ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["payload"] = json.loads(data.pop("payload_json"))
        return data

    def finish(self, key: str, status: str = "completed") -> bool:
        """Encerra a sessão. «completed» guarda o registro; «discarded» o remove."""
        with self._lock, self._connect() as conn:
            if status == "discarded":
                cursor = conn.execute("DELETE FROM session_state WHERE key = ?", (key,))
            else:
                cursor = conn.execute(
                    "UPDATE session_state SET status = 'completed', completed_at = ?, updated_at = ? "
                    "WHERE key = ? AND status = 'active'",
                    (_now(), _now(), key),
                )
            conn.commit()
        return cursor.rowcount > 0

    def attempt_summary(self, exercise_ids: list[str]) -> dict[str, dict]:
        """Resumo das tentativas por exercício: contagem, última nota e datas."""
        if not exercise_ids:
            return {}
        by_exercise: dict[str, list[sqlite3.Row]] = defaultdict(list)
        with self._connect() as conn:
            for start in range(0, len(exercise_ids), 400):
                chunk = exercise_ids[start:start + 400]
                placeholders = ",".join("?" for _ in chunk)
                rows = conn.execute(
                    f"SELECT exercise_id, created_at, is_correct, score FROM attempts "
                    f"WHERE exercise_id IN ({placeholders}) ORDER BY created_at, id",
                    chunk,
                ).fetchall()
                for row in rows:
                    by_exercise[row["exercise_id"]].append(row)
        summary: dict[str, dict] = {}
        for exercise_id, rows in by_exercise.items():
            last = rows[-1]
            graded = [row for row in rows if row["is_correct"] is not None]
            if last["is_correct"] is None:
                last_score = None
            else:
                last_score = float(last["score"] if last["score"] is not None else last["is_correct"])
            summary[exercise_id] = {
                "attempts": len(rows),
                "first_at": rows[0]["created_at"],
                "last_at": last["created_at"],
                "last_score": last_score,
                "pending": last["is_correct"] is None,
                "best_score": max(
                    (float(row["score"] if row["score"] is not None else row["is_correct"]) for row in graded),
                    default=None,
                ),
            }
        return summary


TRANSFER_STAGES = ("construction", "writing_b2", "micro_writing", "speaking_plan", "transfer")


def lesson_step(exercise: dict) -> int:
    """Parte do roteiro da aula (lesson_flow): 0 recuperar, 1 compreender, 2 praticar, 3 transferir."""
    stage = exercise.get("stage")
    kind = exercise.get("type")
    if kind == "flashcard" or stage in ("recall", "retrieval", "spaced_review"):
        return 0
    if kind in ("reading", "listening"):
        return 1
    if kind == "open_text" or stage in TRANSFER_STAGES:
        return 3
    return 2


def lesson_order(unit: dict) -> list[tuple[dict, int]]:
    """Todos os exercícios da aula, inclusive a produção escrita, na ordem do roteiro."""
    steps = len(unit.get("lesson_flow") or []) or 4
    items = [(exercise, min(lesson_step(exercise), steps - 1)) for exercise in unit["exercises"]]
    return sorted(items, key=lambda pair: pair[1])


def unit_session_order(unit: dict) -> list[dict]:
    """Ordem em que a sessão «Estudar» percorre os exercícios de uma unidade.

    Espelha a ordenação de ``startSession`` em app.js: unidades com
    ``lesson_flow`` seguem recuperar → compreender → praticar → produzir.
    """
    items = [exercise for exercise in unit["exercises"] if exercise.get("type") != "open_text"]
    if not unit.get("lesson_flow"):
        return items
    romanian = unit.get("course_id") == "romanian"

    def rank(exercise: dict) -> int:
        stage = exercise.get("stage")
        kind = exercise.get("type")
        if romanian:
            if kind in ("reading", "listening"):
                return 1
            if kind == "flashcard" or stage in ("recall", "retrieval"):
                return 2
            return 3
        if kind == "flashcard" or stage in ("recall", "retrieval", "spaced_review"):
            return 1
        if kind in ("reading", "listening"):
            return 2
        return 3

    return sorted(items, key=rank)
