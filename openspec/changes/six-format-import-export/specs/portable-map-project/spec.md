## ADDED Requirements

### Requirement: Versioned portable package
The `.mtmap` package MUST be a ZIP containing root `manifest.json` and `project.json` documents plus only existing declared assets under `style/`, `data/`, `raster/`, `tiles/`, `icons/`, or `metadata/`. The manifest SHALL record schema version, roles, relative paths, sizes, and SHA-256 hashes.

#### Scenario: Complete project export
- **WHEN** `.mtmap` export is requested
- **THEN** the package contains project state, control/icon points, current style/configuration, and every included source/generated asset declared in the manifest

#### Scenario: No secrets or local paths
- **WHEN** a package is inspected
- **THEN** it contains no credentials, environment settings, absolute paths, or undeclared files

### Requirement: Untrusted archive validation
Import MUST reject traversal/absolute paths, links, duplicate names, encrypted entries, unsupported versions, excessive entry counts, excessive expanded size or compression ratios, missing declarations, hash mismatches, and malformed manifest/project data before persistence.

#### Scenario: Zip Slip attempt
- **WHEN** an archive entry resolves outside the temporary extraction root
- **THEN** import fails and no external or managed file is written

#### Scenario: Hash mismatch
- **WHEN** a declared asset's bytes do not match its manifest hash
- **THEN** import fails with a structured integrity error

### Requirement: Transactional round-trip restoration
Import SHALL generate new project, dataset, point, and related identifiers, remap references, stage only validated assets into managed storage, commit database rows once, and remove staged files on any failure.

#### Scenario: Export then import
- **WHEN** a project is exported to `.mtmap` and imported into the same application
- **THEN** a new independently identified project opens with equivalent name, configuration, features, source data, and available generated artifacts

#### Scenario: Database failure during import
- **WHEN** persistence fails after files are staged
- **THEN** the database transaction is rolled back and the new managed dataset directory is removed
