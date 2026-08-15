"""Small SQLite repository for devices, fixed watchlists and latest snapshots."""

from contextlib import contextmanager
import json
from pathlib import Path
import re
import sqlite3
import threading
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

from .models import DeviceRecord, GatewayBar, GatewaySnapshot, WatchlistSlot


DEFAULT_DEVICE_ID = "device-a"
DEFAULT_DEVICE_NAME = "Device A"
DEFAULT_SYMBOLS = ("600519", "000001", "300750", "688981")
DEFAULT_NAMES = ("贵州茅台", "平安银行", "宁德时代", "中芯国际")
DEVICE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
SYMBOL_RE = re.compile(r"^[0-9]{6}$")
MAX_NAME_LENGTH = 80


class RepositoryError(RuntimeError):
    """The SQLite repository cannot satisfy a requested operation."""


def validate_device_id(value: str) -> str:
    text = str(value).strip()
    if DEVICE_ID_RE.fullmatch(text) is None:
        raise ValueError(
            "device_id must start with an ASCII letter/digit and contain only "
            "ASCII letters, digits, '_' or '-'; maximum 64 characters"
        )
    return text


def validate_symbol(value: str) -> str:
    text = str(value).strip()
    if SYMBOL_RE.fullmatch(text) is None:
        raise ValueError("symbol must be exactly six ASCII digits")
    return text


def validate_name(value: str, field_name: str = "name") -> str:
    text = str(value).strip()
    if not text or len(text) > MAX_NAME_LENGTH:
        raise ValueError("%s must be 1-%d characters" % (field_name, MAX_NAME_LENGTH))
    return text


def _validate_symbols(symbols: Sequence[str]) -> List[str]:
    values = [validate_symbol(symbol) for symbol in symbols]
    if len(values) != 4:
        raise ValueError("watchlist must contain exactly four symbols")
    if len(set(values)) != 4:
        raise ValueError("watchlist symbols must be unique")
    return values


class SQLiteRepository:
    """Thread-safe repository with one latest snapshot row per symbol.

    ``watchlist_slots`` deliberately stores four fixed columns per device.
    This makes the exact-four-slot invariant a SQLite CHECK constraint instead
    of a convention spread across API code and migrations.
    """

    def __init__(self, database_path: str) -> None:
        self.database_path = database_path
        if database_path != ":memory:":
            Path(database_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            database_path,
            check_same_thread=False,
            isolation_level=None,
        )
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._closed = False

    def initialize(self) -> None:
        with self._lock:
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA busy_timeout = 5000")
            if self.database_path != ":memory:":
                self._connection.execute("PRAGMA journal_mode = WAL")
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS devices (
                    device_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 80),
                    created_at TEXT NOT NULL,
                    last_accessed_at TEXT
                );

                CREATE TABLE IF NOT EXISTS watchlist_slots (
                    device_id TEXT PRIMARY KEY
                        REFERENCES devices(device_id) ON DELETE CASCADE,
                    slot_1_symbol TEXT NOT NULL,
                    slot_1_name TEXT,
                    slot_2_symbol TEXT NOT NULL,
                    slot_2_name TEXT,
                    slot_3_symbol TEXT NOT NULL,
                    slot_3_name TEXT,
                    slot_4_symbol TEXT NOT NULL,
                    slot_4_name TEXT,
                    CHECK(length(slot_1_symbol) = 6 AND slot_1_symbol NOT GLOB '*[^0-9]*'),
                    CHECK(length(slot_2_symbol) = 6 AND slot_2_symbol NOT GLOB '*[^0-9]*'),
                    CHECK(length(slot_3_symbol) = 6 AND slot_3_symbol NOT GLOB '*[^0-9]*'),
                    CHECK(length(slot_4_symbol) = 6 AND slot_4_symbol NOT GLOB '*[^0-9]*'),
                    CHECK(slot_1_symbol <> slot_2_symbol),
                    CHECK(slot_1_symbol <> slot_3_symbol),
                    CHECK(slot_1_symbol <> slot_4_symbol),
                    CHECK(slot_2_symbol <> slot_3_symbol),
                    CHECK(slot_2_symbol <> slot_4_symbol),
                    CHECK(slot_3_symbol <> slot_4_symbol)
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS service_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS snapshots (
                    symbol TEXT PRIMARY KEY
                        CHECK(length(symbol) = 6 AND symbol NOT GLOB '*[^0-9]*'),
                    name TEXT,
                    current_price REAL,
                    previous_close REAL,
                    change_amount REAL,
                    change_percent REAL,
                    status TEXT NOT NULL DEFAULT 'UNKNOWN',
                    intraday_json TEXT NOT NULL DEFAULT '[]',
                    intraday_session_date TEXT,
                    quote_data_timestamp TEXT,
                    intraday_data_timestamp TEXT,
                    last_success_at TEXT,
                    quote_fetched_at TEXT,
                    intraday_fetched_at TEXT,
                    quote_source TEXT,
                    intraday_source TEXT,
                    last_error TEXT
                );
                """
            )

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._connection.close()
                self._closed = True

    def __enter__(self) -> "SQLiteRepository":
        return self

    def __exit__(self, _type: Any, _value: Any, _traceback: Any) -> None:
        self.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            if self._closed:
                raise RepositoryError("repository is closed")
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield self._connection
            except Exception:
                self._connection.rollback()
                raise
            else:
                self._connection.commit()

    @staticmethod
    def _now() -> str:
        from datetime import datetime
        from .calendar import SHANGHAI_TZ

        return datetime.now(SHANGHAI_TZ).isoformat()

    def ping(self) -> bool:
        with self._lock:
            try:
                self._connection.execute("SELECT 1").fetchone()
                return True
            except sqlite3.Error:
                return False

    def ensure_seed_device(self) -> DeviceRecord:
        with self._lock:
            row = self._connection.execute(
                "SELECT device_id FROM devices WHERE device_id = ?",
                (DEFAULT_DEVICE_ID,),
            ).fetchone()
        if row is not None:
            return self.get_device(DEFAULT_DEVICE_ID)  # type: ignore[return-value]
        return self.create_device(
            DEFAULT_DEVICE_ID,
            DEFAULT_DEVICE_NAME,
            DEFAULT_SYMBOLS,
            DEFAULT_NAMES,
        )

    def count_devices(self) -> int:
        with self._lock:
            row = self._connection.execute("SELECT COUNT(*) AS count FROM devices").fetchone()
            return int(row["count"])

    def create_device(
        self,
        device_id: str,
        name: str,
        symbols: Sequence[str],
        names: Optional[Sequence[Optional[str]]] = None,
        created_at: Optional[str] = None,
    ) -> DeviceRecord:
        device_id = validate_device_id(device_id)
        name = validate_name(name)
        values = _validate_symbols(symbols)
        slot_names: List[Optional[str]] = [None, None, None, None]
        if names is not None:
            if len(names) != 4:
                raise ValueError("watchlist names must contain exactly four entries")
            for index, value in enumerate(names):
                slot_names[index] = validate_name(value, "slot name") if value else None
        timestamp = created_at or self._now()
        with self._transaction() as connection:
            try:
                connection.execute(
                    "INSERT INTO devices(device_id, name, created_at, last_accessed_at) "
                    "VALUES (?, ?, ?, NULL)",
                    (device_id, name, timestamp),
                )
                connection.execute(
                    """
                    INSERT INTO watchlist_slots(
                        device_id,
                        slot_1_symbol, slot_1_name,
                        slot_2_symbol, slot_2_name,
                        slot_3_symbol, slot_3_name,
                        slot_4_symbol, slot_4_name
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        device_id,
                        values[0], slot_names[0],
                        values[1], slot_names[1],
                        values[2], slot_names[2],
                        values[3], slot_names[3],
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("device_id already exists or violates the device schema") from exc
        return self.get_device(device_id)  # type: ignore[return-value]

    def get_device(self, device_id: str) -> Optional[DeviceRecord]:
        device_id = validate_device_id(device_id)
        with self._lock:
            row = self._connection.execute(
                "SELECT device_id, name, created_at, last_accessed_at "
                "FROM devices WHERE device_id = ?",
                (device_id,),
            ).fetchone()
        if row is None:
            return None
        return DeviceRecord(
            device_id=row["device_id"],
            name=row["name"],
            created_at=row["created_at"],
            last_accessed_at=row["last_accessed_at"],
        )

    def list_devices(self) -> List[DeviceRecord]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT device_id, name, created_at, last_accessed_at "
                "FROM devices ORDER BY device_id"
            ).fetchall()
        return [
            DeviceRecord(
                device_id=row["device_id"],
                name=row["name"],
                created_at=row["created_at"],
                last_accessed_at=row["last_accessed_at"],
            )
            for row in rows
        ]

    def update_device_name(self, device_id: str, name: str) -> DeviceRecord:
        device_id = validate_device_id(device_id)
        name = validate_name(name)
        with self._transaction() as connection:
            cursor = connection.execute(
                "UPDATE devices SET name = ? WHERE device_id = ?",
                (name, device_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(device_id)
        return self.get_device(device_id)  # type: ignore[return-value]

    def delete_device(self, device_id: str) -> None:
        device_id = validate_device_id(device_id)
        with self._transaction() as connection:
            cursor = connection.execute(
                "DELETE FROM devices WHERE device_id = ?", (device_id,)
            )
            if cursor.rowcount != 1:
                raise KeyError(device_id)

    def touch_device_access(self, device_id: str, accessed_at: Optional[str] = None) -> str:
        device_id = validate_device_id(device_id)
        timestamp = accessed_at or self._now()
        with self._transaction() as connection:
            cursor = connection.execute(
                "UPDATE devices SET last_accessed_at = ? WHERE device_id = ?",
                (timestamp, device_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(device_id)
        return timestamp

    def get_watchlist(self, device_id: str) -> List[WatchlistSlot]:
        device_id = validate_device_id(device_id)
        with self._lock:
            row = self._connection.execute(
                """
                SELECT slot_1_symbol, slot_1_name,
                       slot_2_symbol, slot_2_name,
                       slot_3_symbol, slot_3_name,
                       slot_4_symbol, slot_4_name
                FROM watchlist_slots WHERE device_id = ?
                """,
                (device_id,),
            ).fetchone()
        if row is None:
            raise KeyError(device_id)
        return [
            WatchlistSlot(1, row["slot_1_symbol"], row["slot_1_name"]),
            WatchlistSlot(2, row["slot_2_symbol"], row["slot_2_name"]),
            WatchlistSlot(3, row["slot_3_symbol"], row["slot_3_name"]),
            WatchlistSlot(4, row["slot_4_symbol"], row["slot_4_name"]),
        ]

    def save_watchlist(
        self,
        device_id: str,
        symbols: Sequence[str],
        names: Optional[Sequence[Optional[str]]] = None,
    ) -> List[WatchlistSlot]:
        device_id = validate_device_id(device_id)
        values = _validate_symbols(symbols)
        slot_names: List[Optional[str]] = [None, None, None, None]
        if names is not None:
            if len(names) != 4:
                raise ValueError("watchlist names must contain exactly four entries")
            for index, value in enumerate(names):
                slot_names[index] = validate_name(value, "slot name") if value else None
        else:
            existing = self.get_watchlist(device_id)
            names_by_symbol = {item.symbol: item.name for item in existing}
            slot_names = [names_by_symbol.get(symbol) for symbol in values]
        with self._transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE watchlist_slots SET
                    slot_1_symbol = ?, slot_1_name = ?,
                    slot_2_symbol = ?, slot_2_name = ?,
                    slot_3_symbol = ?, slot_3_name = ?,
                    slot_4_symbol = ?, slot_4_name = ?
                WHERE device_id = ?
                """,
                (
                    values[0], slot_names[0],
                    values[1], slot_names[1],
                    values[2], slot_names[2],
                    values[3], slot_names[3],
                    device_id,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError(device_id)
        return self.get_watchlist(device_id)

    def reorder_watchlist(self, device_id: str, slot_order: Sequence[int]) -> List[WatchlistSlot]:
        if len(slot_order) != 4 or set(slot_order) != {1, 2, 3, 4}:
            raise ValueError("slot_order must be a permutation of [1, 2, 3, 4]")
        current = self.get_watchlist(device_id)
        by_slot = {item.slot: item for item in current}
        ordered = [by_slot[int(slot)] for slot in slot_order]
        return self.save_watchlist(
            device_id,
            [item.symbol for item in ordered],
            [item.name for item in ordered],
        )

    def unique_symbols(self) -> List[str]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT slot_1_symbol AS symbol FROM watchlist_slots
                UNION SELECT slot_2_symbol FROM watchlist_slots
                UNION SELECT slot_3_symbol FROM watchlist_slots
                UNION SELECT slot_4_symbol FROM watchlist_slots
                ORDER BY symbol
                """
            ).fetchall()
        return [str(row["symbol"]) for row in rows]

    def upsert_snapshot(self, snapshot: GatewaySnapshot) -> None:
        payload = json.dumps(
            [bar.to_dict() for bar in snapshot.intraday],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO snapshots(
                    symbol, name, current_price, previous_close,
                    change_amount, change_percent, status,
                    intraday_json, intraday_session_date,
                    quote_data_timestamp, intraday_data_timestamp,
                    last_success_at, quote_fetched_at, intraday_fetched_at,
                    quote_source, intraday_source, last_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    name = excluded.name,
                    current_price = excluded.current_price,
                    previous_close = excluded.previous_close,
                    change_amount = excluded.change_amount,
                    change_percent = excluded.change_percent,
                    status = excluded.status,
                    intraday_json = excluded.intraday_json,
                    intraday_session_date = excluded.intraday_session_date,
                    quote_data_timestamp = excluded.quote_data_timestamp,
                    intraday_data_timestamp = excluded.intraday_data_timestamp,
                    last_success_at = excluded.last_success_at,
                    quote_fetched_at = excluded.quote_fetched_at,
                    intraday_fetched_at = excluded.intraday_fetched_at,
                    quote_source = excluded.quote_source,
                    intraday_source = excluded.intraday_source,
                    last_error = excluded.last_error
                """,
                (
                    snapshot.symbol,
                    snapshot.name,
                    snapshot.current_price,
                    snapshot.previous_close,
                    snapshot.change_amount,
                    snapshot.change_percent,
                    snapshot.status,
                    payload,
                    snapshot.intraday_session_date,
                    snapshot.quote_data_timestamp,
                    snapshot.intraday_data_timestamp,
                    snapshot.last_success_at,
                    snapshot.quote_fetched_at,
                    snapshot.intraday_fetched_at,
                    snapshot.quote_source,
                    snapshot.intraday_source,
                    snapshot.last_error,
                ),
            )

    def get_snapshot(self, symbol: str) -> Optional[GatewaySnapshot]:
        symbol = validate_symbol(symbol)
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM snapshots WHERE symbol = ?", (symbol,)
            ).fetchone()
        return self._row_to_snapshot(row) if row is not None else None

    def get_snapshots(self, symbols: Sequence[str]) -> Dict[str, GatewaySnapshot]:
        values = [validate_symbol(symbol) for symbol in symbols]
        return {
            symbol: snapshot
            for symbol in values
            for snapshot in [self.get_snapshot(symbol)]
            if snapshot is not None
        }

    def snapshot_count(self) -> int:
        with self._lock:
            row = self._connection.execute("SELECT COUNT(*) AS count FROM snapshots").fetchone()
            return int(row["count"])

    @staticmethod
    def _row_to_snapshot(row: sqlite3.Row) -> GatewaySnapshot:
        try:
            raw_bars = json.loads(row["intraday_json"] or "[]")
        except (TypeError, ValueError) as exc:
            raise RepositoryError("snapshot intraday_json is not valid JSON") from exc
        bars = tuple(
            GatewayBar.from_dict(item)
            for item in raw_bars[:2000]
            if isinstance(item, Mapping) and item.get("timestamp")
        )
        return GatewaySnapshot(
            symbol=row["symbol"],
            name=row["name"],
            current_price=row["current_price"],
            previous_close=row["previous_close"],
            change_amount=row["change_amount"],
            change_percent=row["change_percent"],
            status=row["status"] or "UNKNOWN",
            intraday=bars,
            intraday_session_date=row["intraday_session_date"],
            quote_data_timestamp=row["quote_data_timestamp"],
            intraday_data_timestamp=row["intraday_data_timestamp"],
            last_success_at=row["last_success_at"],
            quote_fetched_at=row["quote_fetched_at"],
            intraday_fetched_at=row["intraday_fetched_at"],
            quote_source=row["quote_source"],
            intraday_source=row["intraday_source"],
            last_error=row["last_error"],
        )

    def set_setting(self, key: str, value: Any) -> None:
        if not key or len(key) > 120:
            raise ValueError("setting key must be 1-120 characters")
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        with self._transaction() as connection:
            connection.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, text),
            )

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self._connection.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except (TypeError, ValueError):
            return row["value"]

    def set_service_state(self, key: str, value: Any) -> None:
        if not key or len(key) > 120:
            raise ValueError("service state key must be 1-120 characters")
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        with self._transaction() as connection:
            connection.execute(
                "INSERT INTO service_state(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, text),
            )

    def get_service_state(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self._connection.execute(
                "SELECT value FROM service_state WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except (TypeError, ValueError):
            return row["value"]

    def latest_success_at(self, symbols: Optional[Sequence[str]] = None) -> Optional[str]:
        if symbols is None:
            query = "SELECT MAX(last_success_at) AS value FROM snapshots"
            params: Tuple[Any, ...] = ()
        else:
            values = [validate_symbol(symbol) for symbol in symbols]
            if not values:
                return None
            placeholders = ",".join("?" for _ in values)
            query = (
                "SELECT MAX(last_success_at) AS value FROM snapshots "
                "WHERE symbol IN (" + placeholders + ")"
            )
            params = tuple(values)
        with self._lock:
            row = self._connection.execute(query, params).fetchone()
        return row["value"] if row and row["value"] else None
