from collections.abc import Generator
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

import psycopg
from psycopg import Connection
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from models.control_point import ControlPoint
from models.dataset import Dataset


ENV_FILE = Path(__file__).resolve().parent.parent / ".env.local"


class Settings(BaseSettings):
    database_url: str
    max_upload_size_mb: int = Field(default=500, gt=0)

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


class DatabaseError(Exception):
    """The database could not complete an operation."""


class DuplicateDatabaseValue(DatabaseError):
    """A unique database value already exists."""


def _psycopg_database_url(database_url: str) -> str:
    """Remove Prisma-only query options before passing the URL to psycopg."""
    parts = urlsplit(database_url)
    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key.lower() != "pgbouncer"
        ]
    )
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


settings = Settings()


def _dataset_from_row(row: dict[str, object]) -> Dataset:
    return Dataset(
        id=UUID(str(row["id"])),
        filename=str(row["filename"]),
        file_size=int(row["file_size"]),
        content_type=(
            None if row["content_type"] is None else str(row["content_type"])
        ),
        file_hash=str(row["file_hash"]),
        storage_path=str(row["storage_path"]),
        extracted_metadata=dict(row["metadata"]),
        georeferenced_path=(
            None
            if row["georeferenced_path"] is None
            else str(row["georeferenced_path"])
        ),
        georeference_status=str(row["georeference_status"]),
        processed_path=(
            None if row["processed_path"] is None else str(row["processed_path"])
        ),
        process_status=str(row["process_status"]),
        tile_path=None if row["tile_path"] is None else str(row["tile_path"]),
        tile_min_zoom=(
            None if row["tile_min_zoom"] is None else int(row["tile_min_zoom"])
        ),
        tile_max_zoom=(
            None if row["tile_max_zoom"] is None else int(row["tile_max_zoom"])
        ),
        tile_status=str(row["tile_status"]),
        created_at=row["created_at"],
    )


def _control_point_from_row(row: dict[str, object]) -> ControlPoint:
    return ControlPoint(
        id=UUID(str(row["id"])),
        dataset_id=UUID(str(row["dataset_id"])),
        image_x=float(row["image_x"]),
        image_y=float(row["image_y"]),
        longitude=float(row["longitude"]),
        latitude=float(row["latitude"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


DATASET_COLUMNS = """
    id, filename, file_size, content_type, file_hash, storage_path, metadata,
    georeferenced_path, georeference_status, processed_path, process_status,
    tile_path, tile_min_zoom, tile_max_zoom, tile_status, created_at
"""
CONTROL_POINT_COLUMNS = """
    id, dataset_id, image_x, image_y, longitude, latitude, created_at, updated_at
"""


class DatabaseSession:
    def __init__(self, connection: Connection[dict[str, object]]) -> None:
        self.connection = connection

    def get_dataset(self, dataset_id: UUID) -> Dataset | None:
        try:
            row = self.connection.execute(
                f"SELECT {DATASET_COLUMNS} FROM datasets WHERE id = %s",
                (dataset_id,),
            ).fetchone()
            return None if row is None else _dataset_from_row(row)
        except psycopg.Error as exc:
            raise DatabaseError from exc

    def find_dataset_by_hash(self, file_hash: str) -> Dataset | None:
        try:
            row = self.connection.execute(
                f"SELECT {DATASET_COLUMNS} FROM datasets WHERE file_hash = %s",
                (file_hash,),
            ).fetchone()
            return None if row is None else _dataset_from_row(row)
        except psycopg.Error as exc:
            raise DatabaseError from exc

    def list_datasets(self) -> list[Dataset]:
        try:
            rows = self.connection.execute(
                f"SELECT {DATASET_COLUMNS} FROM datasets "
                "ORDER BY created_at DESC, id DESC"
            ).fetchall()
            return [_dataset_from_row(row) for row in rows]
        except psycopg.Error as exc:
            raise DatabaseError from exc

    def insert_dataset(self, dataset: Dataset) -> None:
        try:
            row = self.connection.execute(
                """
                INSERT INTO datasets (
                    id, filename, file_size, content_type, file_hash, storage_path,
                    metadata, georeferenced_path, georeference_status,
                    processed_path, process_status, tile_path, tile_min_zoom,
                    tile_max_zoom, tile_status, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s
                )
                RETURNING created_at
                """,
                (
                    dataset.id,
                    dataset.filename,
                    dataset.file_size,
                    dataset.content_type,
                    dataset.file_hash,
                    dataset.storage_path,
                    Jsonb(dataset.extracted_metadata),
                    dataset.georeferenced_path,
                    dataset.georeference_status,
                    dataset.processed_path,
                    dataset.process_status,
                    dataset.tile_path,
                    dataset.tile_min_zoom,
                    dataset.tile_max_zoom,
                    dataset.tile_status,
                    dataset.created_at,
                ),
            ).fetchone()
            dataset.created_at = row["created_at"]
        except UniqueViolation as exc:
            raise DuplicateDatabaseValue from exc
        except psycopg.Error as exc:
            raise DatabaseError from exc

    def save_dataset(self, dataset: Dataset) -> None:
        try:
            self.connection.execute(
                """
                UPDATE datasets SET
                    filename = %s, file_size = %s, content_type = %s,
                    file_hash = %s, storage_path = %s, metadata = %s,
                    georeferenced_path = %s, georeference_status = %s,
                    processed_path = %s, process_status = %s, tile_path = %s,
                    tile_min_zoom = %s, tile_max_zoom = %s, tile_status = %s
                WHERE id = %s
                """,
                (
                    dataset.filename,
                    dataset.file_size,
                    dataset.content_type,
                    dataset.file_hash,
                    dataset.storage_path,
                    Jsonb(dataset.extracted_metadata),
                    dataset.georeferenced_path,
                    dataset.georeference_status,
                    dataset.processed_path,
                    dataset.process_status,
                    dataset.tile_path,
                    dataset.tile_min_zoom,
                    dataset.tile_max_zoom,
                    dataset.tile_status,
                    dataset.id,
                ),
            )
        except UniqueViolation as exc:
            raise DuplicateDatabaseValue from exc
        except psycopg.Error as exc:
            raise DatabaseError from exc

    def delete_dataset(self, dataset_id: UUID) -> None:
        try:
            self.connection.execute("DELETE FROM datasets WHERE id = %s", (dataset_id,))
        except psycopg.Error as exc:
            raise DatabaseError from exc

    def get_control_point(self, control_point_id: UUID) -> ControlPoint | None:
        try:
            row = self.connection.execute(
                f"SELECT {CONTROL_POINT_COLUMNS} FROM control_points WHERE id = %s",
                (control_point_id,),
            ).fetchone()
            return None if row is None else _control_point_from_row(row)
        except psycopg.Error as exc:
            raise DatabaseError from exc

    def list_control_points(self, dataset_id: UUID) -> list[ControlPoint]:
        try:
            rows = self.connection.execute(
                f"SELECT {CONTROL_POINT_COLUMNS} FROM control_points "
                "WHERE dataset_id = %s ORDER BY created_at, id",
                (dataset_id,),
            ).fetchall()
            return [_control_point_from_row(row) for row in rows]
        except psycopg.Error as exc:
            raise DatabaseError from exc

    def insert_control_point(self, point: ControlPoint) -> None:
        try:
            row = self.connection.execute(
                """
                INSERT INTO control_points (
                    id, dataset_id, image_x, image_y, longitude, latitude,
                    created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING created_at, updated_at
                """,
                (
                    point.id,
                    point.dataset_id,
                    point.image_x,
                    point.image_y,
                    point.longitude,
                    point.latitude,
                    point.created_at,
                    point.updated_at,
                ),
            ).fetchone()
            point.created_at = row["created_at"]
            point.updated_at = row["updated_at"]
        except psycopg.Error as exc:
            raise DatabaseError from exc

    def save_control_point(self, point: ControlPoint) -> None:
        try:
            row = self.connection.execute(
                """
                UPDATE control_points SET
                    image_x = %s, image_y = %s, longitude = %s, latitude = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING updated_at
                """,
                (
                    point.image_x,
                    point.image_y,
                    point.longitude,
                    point.latitude,
                    point.id,
                ),
            ).fetchone()
            if row is not None:
                point.updated_at = row["updated_at"]
        except psycopg.Error as exc:
            raise DatabaseError from exc

    def delete_control_point(self, control_point_id: UUID) -> None:
        try:
            self.connection.execute(
                "DELETE FROM control_points WHERE id = %s",
                (control_point_id,),
            )
        except psycopg.Error as exc:
            raise DatabaseError from exc

    def ping(self) -> None:
        try:
            self.connection.execute("SELECT 1").fetchone()
        except psycopg.Error as exc:
            raise DatabaseError from exc

    def commit(self) -> None:
        try:
            self.connection.commit()
        except psycopg.Error as exc:
            raise DatabaseError from exc

    def rollback(self) -> None:
        self.connection.rollback()

    def close(self) -> None:
        self.connection.close()


def get_db() -> Generator[DatabaseSession, None, None]:
    connection = psycopg.connect(
        _psycopg_database_url(settings.database_url),
        row_factory=dict_row,
        prepare_threshold=None,
    )
    database = DatabaseSession(connection)
    try:
        yield database
    finally:
        database.close()
