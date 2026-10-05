-- CreateSchema
CREATE SCHEMA IF NOT EXISTS "public";

-- CreateTable
CREATE TABLE "datasets" (
    "id" UUID NOT NULL,
    "filename" TEXT NOT NULL,
    "file_size" BIGINT NOT NULL,
    "content_type" TEXT,
    "file_hash" TEXT NOT NULL,
    "storage_path" TEXT NOT NULL,
    "metadata" JSONB NOT NULL,
    "georeferenced_path" TEXT,
    "georeference_status" TEXT NOT NULL DEFAULT 'not_started',
    "processed_path" TEXT,
    "process_status" TEXT NOT NULL DEFAULT 'not_started',
    "tile_path" TEXT,
    "tile_min_zoom" INTEGER,
    "tile_max_zoom" INTEGER,
    "tile_status" TEXT NOT NULL DEFAULT 'not_started',
    "created_at" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "datasets_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "control_points" (
    "id" UUID NOT NULL,
    "dataset_id" UUID NOT NULL,
    "image_x" DOUBLE PRECISION NOT NULL,
    "image_y" DOUBLE PRECISION NOT NULL,
    "longitude" DOUBLE PRECISION NOT NULL,
    "latitude" DOUBLE PRECISION NOT NULL,
    "created_at" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "control_points_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "datasets_file_hash_key" ON "datasets"("file_hash");

-- CreateIndex
CREATE INDEX "control_points_dataset_id_idx" ON "control_points"("dataset_id");

-- AddForeignKey
ALTER TABLE "control_points" ADD CONSTRAINT "control_points_dataset_id_fkey" FOREIGN KEY ("dataset_id") REFERENCES "datasets"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- Keep Supabase Data API access closed until explicit ownership policies exist.
ALTER TABLE "datasets" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "control_points" ENABLE ROW LEVEL SECURITY;
