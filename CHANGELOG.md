# Change Log

The format is based on [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)
and this project adheres to [Semantic Versioning](http://semver.org/).

## [Unreleased] - 2025-05-14

## [1.1.0] - 2025-05-14

### Added

**UI**:

- AI Generated Dockerfile
- Auto-fix Vulnerability
- Add platform mail settings
- Add platform and mail notifications

**API**:

- add email notification support
- add teams notification support
- add ai generated dockerfile support
- add user notification support

### Changed

- **Gitlab**: upgrade version to `17.8.7`
- DevOps:
    - **Gitlab Runner**: upgrade version to `17.8.5`
- **API**: upgrade version to `1.1.0`
    - update dependency to lastest version
    - change environment variable reading method
    - fix email templates with i18n support
    - fix api return base
    - rewrite database context
- **UI**: upgrade version to `1.1.0`
    - Fix commit hook-issue search parameter
    - Fix default project template
    - Fix WBS update issue bug
    - Update issue list route name

## [1.0.0] - 2025-01-24

### Changed

- We release a **FastAPI** version of API as V3 API
- Use V3 UI
