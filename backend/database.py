from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from models.control_point import ControlPoint
from models.dataset import Dataset
from models.icon_point import IconPoint
from models.map_project import MapProject
from models.tables import (
    Base,
    ControlPointRecord,
    DatasetRecord,
    GeoreferenceConfig,
    IconPointRecord,
    MapProjectRecord,
)


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


def _sqlalchemy_database_url(database_url: str) -> str:
    parts = urlsplit(database_url)
    scheme = parts.scheme
    if scheme.startswith("sqlite"):
        return database_url
    if scheme in {"postgres", "postgresql"}:
        scheme = "postgresql+psycopg"
    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key.lower() != "pgbouncer"
        ]
    )
    return urlunsplit((scheme, parts.netloc, parts.path, query, parts.fragment))


settings = Settings()

# Supabase session/transaction pooler does not support prepared statements
engine_kwargs = {"pool_pre_ping": True}
if "pgbouncer=true" in settings.database_url.lower():
    engine_kwargs["connect_args"] = {"prepare_threshold": None}

engine = create_engine(
    _sqlalchemy_database_url(settings.database_url),
    **engine_kwargs
)
SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)


def initialize_database() -> None:
    Base.metadata.create_all(bind=engine)


def _dataset_from_record(record: DatasetRecord) -> Dataset:
    return Dataset(
        id=record.id,
        filename=record.filename,
        file_size=record.file_size,
        content_type=record.content_type,
        file_hash=record.file_hash,
        storage_path=record.storage_path,
        extracted_metadata=dict(record.metadata_value),
        georeferenced_path=record.georeferenced_path,
        georeference_status=record.georeference_status,
        processed_path=record.processed_path,
        process_status=record.process_status,
        tile_path=record.tile_path,
        tile_min_zoom=record.tile_min_zoom,
        tile_max_zoom=record.tile_max_zoom,
        tile_status=record.tile_status,
        created_at=record.created_at,
    )


def _control_point_from_record(record: ControlPointRecord) -> ControlPoint:
    return ControlPoint(
        id=record.id,
        dataset_id=record.dataset_id,
        image_x=record.image_x,
        image_y=record.image_y,
        longitude=record.longitude,
        latitude=record.latitude,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _icon_point_from_record(record: IconPointRecord) -> IconPoint:
    return IconPoint(
        id=record.id,
        dataset_id=record.dataset_id,
        icon_key=record.icon_key,
        latitude=record.latitude,
        longitude=record.longitude,
        description=record.description,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _map_project_from_record(record: MapProjectRecord) -> MapProject:
    return MapProject(
        id=record.id,
        name=record.name,
        dataset_id=record.dataset_id,
        configuration=dict(record.configuration),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


class DatabaseSession:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_map_project(self, project_id: UUID) -> MapProject | None:
        try:
            record = self.session.get(MapProjectRecord, project_id)
            return None if record is None else _map_project_from_record(record)
        except SQLAlchemyError as exc:
            raise DatabaseError from exc

    def get_map_project_by_dataset_id(self, dataset_id: UUID) -> MapProject | None:
        try:
            record = self.session.scalar(
                select(MapProjectRecord).where(MapProjectRecord.dataset_id == dataset_id).order_by(MapProjectRecord.created_at.desc())
            )
            return None if record is None else _map_project_from_record(record)
        except SQLAlchemyError as exc:
            raise DatabaseError from exc

    def insert_map_project(self, project: MapProject) -> None:
        record = MapProjectRecord(
            id=project.id,
            name=project.name,
            dataset_id=project.dataset_id,
            configuration=project.configuration,
            created_at=project.created_at,
            updated_at=project.updated_at,
        )
        try:
            self.session.add(record)
            self.session.flush()
            project.created_at = record.created_at
            project.updated_at = record.updated_at
        except IntegrityError as exc:
            raise DuplicateDatabaseValue from exc
        except SQLAlchemyError as exc:
            raise DatabaseError from exc

    def save_map_project(self, project: MapProject) -> None:
        try:
            record = self.session.get(MapProjectRecord, project.id)
            if record is None:
                raise DatabaseError("Map project does not exist.")
            record.name = project.name
            record.dataset_id = project.dataset_id
            record.configuration = project.configuration
            record.updated_at = datetime.now(timezone.utc)
            self.session.flush()
            project.updated_at = record.updated_at
        except IntegrityError as exc:
            raise DuplicateDatabaseValue from exc
        except SQLAlchemyError as exc:
            raise DatabaseError from exc

    def get_dataset(self, dataset_id: UUID) -> Dataset | None:
        try:
            record = self.session.get(DatasetRecord, dataset_id)
            return None if record is None else _dataset_from_record(record)
        except SQLAlchemyError as exc:
            raise DatabaseError from exc

    def find_dataset_by_hash(self, file_hash: str) -> Dataset | None:
        try:
            record = self.session.scalar(
                select(DatasetRecord).where(DatasetRecord.file_hash == file_hash)
            )
            return None if record is None else _dataset_from_record(record)
        except SQLAlchemyError as exc:
            raise DatabaseError from exc

    def list_datasets(self) -> list[Dataset]:
        try:
            records = self.session.scalars(
                select(DatasetRecord).order_by(
                    DatasetRecord.created_at.desc(), DatasetRecord.id.desc()
                )
            ).all()
            return [_dataset_from_record(record) for record in records]
        except SQLAlchemyError as exc:
            raise DatabaseError from exc

    def insert_dataset(self, dataset: Dataset) -> None:
        record = DatasetRecord(
            id=dataset.id,
            filename=dataset.filename,
            file_size=dataset.file_size,
            content_type=dataset.content_type,
            file_hash=dataset.file_hash,
            storage_path=dataset.storage_path,
            metadata_value=dataset.extracted_metadata,
            georeferenced_path=dataset.georeferenced_path,
            georeference_status=dataset.georeference_status,
            processed_path=dataset.processed_path,
            process_status=dataset.process_status,
            tile_path=dataset.tile_path,
            tile_min_zoom=dataset.tile_min_zoom,
            tile_max_zoom=dataset.tile_max_zoom,
            tile_status=dataset.tile_status,
            created_at=dataset.created_at,
        )
        try:
            self.session.add(record)
            self.session.flush()
            dataset.created_at = record.created_at
        except IntegrityError as exc:
            raise DuplicateDatabaseValue from exc
        except SQLAlchemyError as exc:
            raise DatabaseError from exc

    def save_dataset(self, dataset: Dataset) -> None:
        try:
            record = self.session.get(DatasetRecord, dataset.id)
            if record is None:
                raise DatabaseError("Dataset does not exist.")
            for name, value in {
                "filename": dataset.filename,
                "file_size": dataset.file_size,
                "content_type": dataset.content_type,
                "file_hash": dataset.file_hash,
                "storage_path": dataset.storage_path,
                "metadata_value": dataset.extracted_metadata,
                "georeferenced_path": dataset.georeferenced_path,
                "georeference_status": dataset.georeference_status,
                "processed_path": dataset.processed_path,
                "process_status": dataset.process_status,
                "tile_path": dataset.tile_path,
                "tile_min_zoom": dataset.tile_min_zoom,
                "tile_max_zoom": dataset.tile_max_zoom,
                "tile_status": dataset.tile_status,
            }.items():
                setattr(record, name, value)
            self.session.flush()
        except IntegrityError as exc:
            raise DuplicateDatabaseValue from exc
        except SQLAlchemyError as exc:
            raise DatabaseError from exc

    def delete_dataset(self, dataset_id: UUID) -> None:
        try:
            record = self.session.get(DatasetRecord, dataset_id)
            if record is not None:
                self.session.delete(record)
                self.session.flush()
        except SQLAlchemyError as exc:
            raise DatabaseError from exc

    def get_control_point(self, control_point_id: UUID) -> ControlPoint | None:
        try:
            record = self.session.get(ControlPointRecord, control_point_id)
            return None if record is None else _control_point_from_record(record)
        except SQLAlchemyError as exc:
            raise DatabaseError from exc

    def list_control_points(self, dataset_id: UUID) -> list[ControlPoint]:
        try:
            records = self.session.scalars(
                select(ControlPointRecord)
                .where(ControlPointRecord.dataset_id == dataset_id)
                .order_by(ControlPointRecord.created_at, ControlPointRecord.id)
            ).all()
            return [_control_point_from_record(record) for record in records]
        except SQLAlchemyError as exc:
            raise DatabaseError from exc

    def insert_control_point(self, point: ControlPoint) -> None:
        record = ControlPointRecord(
            id=point.id,
            dataset_id=point.dataset_id,
            image_x=point.image_x,
            image_y=point.image_y,
            longitude=point.longitude,
            latitude=point.latitude,
            created_at=point.created_at,
            updated_at=point.updated_at,
        )
        try:
            self.session.add(record)
            self.session.flush()
            point.created_at = record.created_at
            point.updated_at = record.updated_at
        except SQLAlchemyError as exc:
            raise DatabaseError from exc

    def save_control_point(self, point: ControlPoint) -> None:
        try:
            record = self.session.get(ControlPointRecord, point.id)
            if record is None:
                raise DatabaseError("Control point does not exist.")
            record.image_x = point.image_x
            record.image_y = point.image_y
            record.longitude = point.longitude
            record.latitude = point.latitude
            record.updated_at = datetime.now(timezone.utc)
            self.session.flush()
            point.updated_at = record.updated_at
        except SQLAlchemyError as exc:
            raise DatabaseError from exc

    def delete_control_point(self, control_point_id: UUID) -> None:
        try:
            record = self.session.get(ControlPointRecord, control_point_id)
            if record is not None:
                self.session.delete(record)
                self.session.flush()
        except SQLAlchemyError as exc:
            raise DatabaseError from exc

    def get_active_georeference_config(
        self, dataset_id: UUID
    ) -> GeoreferenceConfig | None:
        try:
            return self.session.scalar(
                select(GeoreferenceConfig).where(
                    GeoreferenceConfig.dataset_id == dataset_id,
                    GeoreferenceConfig.is_active.is_(True),
                )
            )
        except SQLAlchemyError as exc:
            raise DatabaseError from exc

    def save_georeference_config(self, config: GeoreferenceConfig) -> None:
        try:
            self.session.add(config)
            self.session.flush()
        except SQLAlchemyError as exc:
            raise DatabaseError from exc

    def mark_georeference_config_pending(self, dataset_id: UUID) -> None:
        config = self.get_active_georeference_config(dataset_id)
        if config is not None:
            config.status = "pending"
            config.updated_at = datetime.now(timezone.utc)

    def get_icon_point(self, icon_point_id: UUID) -> IconPoint | None:
        try:
            record = self.session.get(IconPointRecord, icon_point_id)
            return None if record is None else _icon_point_from_record(record)
        except SQLAlchemyError as exc:
            raise DatabaseError from exc

    def list_icon_points(self, dataset_id: UUID) -> list[IconPoint]:
        try:
            records = self.session.scalars(
                select(IconPointRecord)
                .where(IconPointRecord.dataset_id == dataset_id)
                .order_by(IconPointRecord.created_at, IconPointRecord.id)
            ).all()
            return [_icon_point_from_record(record) for record in records]
        except SQLAlchemyError as exc:
            raise DatabaseError from exc

    def insert_icon_point(self, point: IconPoint) -> None:
        record = IconPointRecord(
            id=point.id,
            dataset_id=point.dataset_id,
            icon_key=point.icon_key,
            latitude=point.latitude,
            longitude=point.longitude,
            description=point.description,
            created_at=point.created_at,
            updated_at=point.updated_at,
        )
        try:
            self.session.add(record)
            self.session.flush()
            point.created_at = record.created_at
            point.updated_at = record.updated_at
        except SQLAlchemyError as exc:
            raise DatabaseError from exc

    def save_icon_point(self, point: IconPoint) -> None:
        try:
            record = self.session.get(IconPointRecord, point.id)
            if record is None:
                raise DatabaseError("Icon point does not exist.")
            record.icon_key = point.icon_key
            record.latitude = point.latitude
            record.longitude = point.longitude
            record.description = point.description
            record.updated_at = datetime.now(timezone.utc)
            self.session.flush()
            point.updated_at = record.updated_at
        except SQLAlchemyError as exc:
            raise DatabaseError from exc

    def delete_icon_point(self, icon_point_id: UUID) -> None:
        try:
            record = self.session.get(IconPointRecord, icon_point_id)
            if record is not None:
                self.session.delete(record)
                self.session.flush()
        except SQLAlchemyError as exc:
            raise DatabaseError from exc



    def ping(self) -> None:
        try:
            self.session.execute(text("SELECT 1")).scalar_one()
        except SQLAlchemyError as exc:
            raise DatabaseError from exc

    def commit(self) -> None:
        try:
            self.session.commit()
        except SQLAlchemyError as exc:
            raise DatabaseError from exc

    def rollback(self) -> None:
        self.session.rollback()

    def close(self) -> None:
        self.session.close()


def get_db() -> Generator[DatabaseSession, None, None]:
    database = DatabaseSession(SessionFactory())
    try:
        yield database
    finally:
        database.close()
