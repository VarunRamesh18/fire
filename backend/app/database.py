"""
FireGuard AI - SQLite storage.

* ``transitions`` - one row per pipeline state change (not per frame).
* ``incidents``   - one row per incident with outcome, key metrics and full timeline.

All timestamps are ISO-8601 UTC with an explicit offset, so browsers convert
them to local time correctly.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

import aiosqlite

from app.config import settings

logger = logging.getLogger("fireguard.database")

_conn: Optional[aiosqlite.Connection] = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS transitions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     TEXT NOT NULL,
    incident_id   TEXT,
    from_state    TEXT NOT NULL,
    to_state      TEXT NOT NULL,
    note          TEXT,
    confidence    REAL,
    smoke_ppm     REAL,
    distance_m    REAL,
    pressure_bar  REAL
);
CREATE INDEX IF NOT EXISTS idx_transitions_ts ON transitions(timestamp);
CREATE TABLE IF NOT EXISTS incidents (
    id                 TEXT PRIMARY KEY,
    started_at         TEXT NOT NULL,
    ended_at           TEXT NOT NULL,
    outcome            TEXT NOT NULL,
    reason             TEXT,
    duration_s         REAL,
    peak_confidence    REAL,
    t_confirmed_s      REAL,
    t_suppression_s    REAL,
    t_extinguished_s   REAL,
    distance_m         REAL,
    pump_pressure_bar  REAL,
    flow_lpm           REAL,
    water_used_l       REAL,
    metrics_json       TEXT NOT NULL,
    timeline_json      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_incidents_started ON incidents(started_at);
"""


async def init_db(path: Optional[str] = None) -> None:
    global _conn
    _conn = await aiosqlite.connect(str(settings.path(path or settings.DB_PATH)))
    _conn.row_factory = aiosqlite.Row
    await _conn.executescript(SCHEMA)
    await _conn.commit()
    logger.info("Database ready at %s", settings.path(path or settings.DB_PATH))


async def close_db() -> None:
    global _conn
    if _conn is not None:
        await _conn.close()
        _conn = None


def _db() -> aiosqlite.Connection:
    if _conn is None:
        raise RuntimeError("Database not initialised")
    return _conn


# ---------------------------------------------------------------------------
# writes
# ---------------------------------------------------------------------------


async def save_transition(ev: Dict[str, Any]) -> None:
    await _db().execute(
        "INSERT INTO transitions (timestamp, incident_id, from_state, to_state, note, confidence, smoke_ppm,"
        " distance_m, pressure_bar) VALUES (?,?,?,?,?,?,?,?,?)",
        (ev["at"], ev.get("incident_id"), ev["from"], ev["to"], ev.get("note"), ev.get("confidence"),
         ev.get("smoke_ppm"), ev.get("distance_m"), ev.get("pressure_bar")),
    )
    await _db().commit()


async def save_incident(rep: Dict[str, Any]) -> None:
    m = rep["metrics"]
    await _db().execute(
        "INSERT OR REPLACE INTO incidents (id, started_at, ended_at, outcome, reason, duration_s, peak_confidence,"
        " t_confirmed_s, t_suppression_s, t_extinguished_s, distance_m, pump_pressure_bar, flow_lpm, water_used_l,"
        " metrics_json, timeline_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (rep["id"], rep["started_at"], rep["ended_at"], rep["outcome"], rep.get("reason"), rep["duration_s"],
         m.get("peak_confidence"), m.get("t_confirmed_s"), m.get("t_suppression_s"), m.get("t_extinguished_s"),
         m.get("distance_m"), m.get("pump_pressure_bar"), m.get("flow_lpm"), m.get("water_used_l"),
         json.dumps(m), json.dumps(rep["timeline"])),
    )
    await _db().commit()


# ---------------------------------------------------------------------------
# reads
# ---------------------------------------------------------------------------


def _range(start: Optional[str], end: Optional[str], col: str) -> Tuple[str, List[Any]]:
    clauses, params = [], []
    if start:
        clauses.append(f"{col} >= ?")
        params.append(start)
    if end:
        clauses.append(f"{col} < ?")
        params.append(end)
    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


async def get_transitions(limit: int, offset: int, start: Optional[str] = None,
                          end: Optional[str] = None) -> Tuple[List[Dict[str, Any]], int]:
    where, params = _range(start, end, "timestamp")
    cur = await _db().execute(f"SELECT COUNT(*) FROM transitions {where}", params)
    total = (await cur.fetchone())[0]
    cur = await _db().execute(f"SELECT * FROM transitions {where} ORDER BY id DESC LIMIT ? OFFSET ?",
                              [*params, limit, offset])
    return [dict(r) for r in await cur.fetchall()], total


def _incident_row(r: aiosqlite.Row) -> Dict[str, Any]:
    d = dict(r)
    d["metrics"] = json.loads(d.pop("metrics_json"))
    d["timeline"] = json.loads(d.pop("timeline_json"))
    return d


async def get_incidents(limit: int, offset: int, start: Optional[str] = None,
                        end: Optional[str] = None) -> Tuple[List[Dict[str, Any]], int]:
    where, params = _range(start, end, "started_at")
    cur = await _db().execute(f"SELECT COUNT(*) FROM incidents {where}", params)
    total = (await cur.fetchone())[0]
    cur = await _db().execute(f"SELECT * FROM incidents {where} ORDER BY started_at DESC LIMIT ? OFFSET ?",
                              [*params, limit, offset])
    return [_incident_row(r) for r in await cur.fetchall()], total


async def get_stats() -> Dict[str, Any]:
    db = _db()
    cur = await db.execute("SELECT outcome, COUNT(*) AS n FROM incidents GROUP BY outcome")
    by_outcome = {r["outcome"]: r["n"] for r in await cur.fetchall()}
    cur = await db.execute(
        "SELECT AVG(t_confirmed_s) AS confirm, AVG(t_suppression_s) AS suppress, AVG(t_extinguished_s) AS extinguish,"
        " AVG(pump_pressure_bar) AS pressure, AVG(distance_m) AS distance, SUM(water_used_l) AS water,"
        " AVG(peak_confidence) AS conf FROM incidents WHERE outcome = 'EXTINGUISHED'")
    r = await cur.fetchone()
    cur = await db.execute("SELECT COUNT(*) FROM transitions")
    transitions = (await cur.fetchone())[0]

    def rnd(v: Any, n: int = 2) -> Optional[float]:
        return round(v, n) if v is not None else None

    return {
        "total_incidents": sum(by_outcome.values()),
        "by_outcome": by_outcome,
        "extinguished": by_outcome.get("EXTINGUISHED", 0),
        "false_alarms_rejected": by_outcome.get("FALSE_ALARM_REJECTED", 0),
        "operator_alerts": by_outcome.get("VISION_ONLY_ALERT", 0) + by_outcome.get("SMOKE_ONLY_ALERT", 0),
        "escalated": by_outcome.get("ESCALATED", 0),
        "avg_time_to_confirm_s": rnd(r["confirm"]),
        "avg_time_to_suppression_s": rnd(r["suppress"]),
        "avg_time_to_extinguish_s": rnd(r["extinguish"]),
        "avg_pump_pressure_bar": rnd(r["pressure"]),
        "avg_distance_m": rnd(r["distance"]),
        "total_water_l": rnd(r["water"]),
        "avg_peak_confidence": rnd(r["conf"], 3),
        "transitions": transitions,
    }


async def export_csv() -> str:
    cur = await _db().execute("SELECT * FROM incidents ORDER BY started_at DESC")
    rows = await cur.fetchall()
    out = io.StringIO()
    cols = ["id", "started_at", "ended_at", "outcome", "reason", "duration_s", "peak_confidence", "t_confirmed_s",
            "t_suppression_s", "t_extinguished_s", "distance_m", "pump_pressure_bar", "flow_lpm", "water_used_l"]
    w = csv.writer(out)
    w.writerow(cols)
    for r in rows:
        w.writerow([r[c] for c in cols])
    return out.getvalue()
