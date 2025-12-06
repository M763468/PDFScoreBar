# External Repositories

This directory contains third-party repositories used in the project.

## Contents
- **`homr/`**: Clone of the [homr](https://github.com/liebharc/homr) repository (Barline detection).
- **`oemer/`**: Clone of the [oemer](https://github.com/BreezeWhite/oemer) repository (OMR library).


## Usage Note
- **`oemer/`**: **Managed as a Git submodule**. It tracks a specific commit of the upstream repository.
- **`homr/`**: **Plain clone (Untracked)**. It is a nested repository, not a submodule. Treat it as a local reference copy.
- Docker environments may mount their own internal copies of these libraries.
- Use these local copies primarily for reference, debugging, or experimental modifications.
