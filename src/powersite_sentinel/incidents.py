"""Persistent local incident lifecycle derived from current findings."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

from powersite_sentinel.models import Finding

_SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    incident_id TEXT PRIMARY KEY,
    site_uid TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    code TEXT NOT NULL,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    status TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    resolved_at TEXT,
    occurrences INTEGER NOT NULL,
    evidence_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_incidents_site_status ON incidents(site_uid, status, last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_incidents_fingerprint ON incidents(site_uid, fingerprint, status);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


class IncidentStore:
    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.executescript(_SCHEMA)
        return connection

    async def reconcile(self, site_uid: str, findings: list[Finding]) -> list[dict[str, object]]:
        return await asyncio.to_thread(self._reconcile, site_uid, findings)

    def _reconcile(self, site_uid: str, findings: list[Finding]) -> list[dict[str, object]]:
        now = _now()
        active = {item.fingerprint: item for item in findings if item.severity != "info"}
        with self._connect() as db:
            open_rows = db.execute(
                "SELECT * FROM incidents WHERE site_uid=? AND status='open'",
                (site_uid,),
            ).fetchall()
            open_by_fingerprint = {str(row["fingerprint"]): row for row in open_rows}
            for fingerprint, finding in active.items():
                existing = open_by_fingerprint.get(fingerprint)
                evidence_json = json.dumps(finding.evidence, sort_keys=True, separators=(",", ":"))
                if existing is None:
                    db.execute(
                        """
                        INSERT INTO incidents(
                            incident_id, site_uid, fingerprint, code, severity, title, summary,
                            status, first_seen, last_seen, resolved_at, occurrences, evidence_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, NULL, 1, ?)
                        """,
                        (
                            f"inc_{uuid.uuid4().hex}",
                            site_uid,
                            fingerprint,
                            finding.code,
                            finding.severity,
                            finding.title,
                            finding.summary,
                            now,
                            now,
                            evidence_json,
                        ),
                    )
                else:
                    db.execute(
                        """
                        UPDATE incidents
                        SET severity=?, title=?, summary=?, last_seen=?,
                            occurrences=occurrences+1, evidence_json=?
                        WHERE incident_id=?
                        """,
                        (
                            finding.severity,
                            finding.title,
                            finding.summary,
                            now,
                            evidence_json,
                            existing["incident_id"],
                        ),
                    )
            for fingerprint, row in open_by_fingerprint.items():
                if fingerprint not in active:
                    db.execute(
                        (
                            "UPDATE incidents SET status='resolved', resolved_at=?, "
                            "last_seen=? WHERE incident_id=?"
                        ),
                        (now, now, row["incident_id"]),
                    )
            db.commit()
        return self._list(site_uid=site_uid, status="open", limit=200)

    async def list(
        self,
        *,
        site_uid: str | None = None,
        status: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, object]]:
        return await asyncio.to_thread(self._list, site_uid=site_uid, status=status, limit=limit)

    def _list(
        self,
        *,
        site_uid: str | None,
        status: str | None,
        limit: int,
    ) -> list[dict[str, object]]:
        clauses: list[str] = []
        values: list[object] = []
        if site_uid:
            clauses.append("site_uid=?")
            values.append(site_uid)
        if status:
            clauses.append("status=?")
            values.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        values.append(limit)
        with self._connect() as db:
            rows = db.execute(
                f"SELECT * FROM incidents {where} ORDER BY last_seen DESC LIMIT ?",  # noqa: S608
                values,
            ).fetchall()
        output: list[dict[str, object]] = []
        for row in rows:
            item = dict(row)
            item["evidence"] = json.loads(str(item.pop("evidence_json")))
            output.append(item)
        return output
