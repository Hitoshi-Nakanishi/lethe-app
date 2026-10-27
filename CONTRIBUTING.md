# Contributing

Report the expected result, actual result, reproduction steps, OS and Python version. Use fictional examples and remove private
audio, transcripts, names, paths and credentials from attachments.

## Development

Use the existing project environment with Python 3.14.4. From the checkout:

```sh
task setup
task default
```

`task default` runs formatting, lint, type checks and tests. Use `task test` or `uv run --no-sync pytest -q` for tests alone.
The [CI workflow](.github/workflows/tests.yml) checks Windows and macOS and builds the package.

Keep changes small and cover changed behavior. Tests use temporary files and mocks; they do not need a microphone or downloaded
models. Preserve local processing and both supported platforms. Recordings, model caches, sessions and local settings stay out
of Git.

See [architecture](docs/architecture.md) for source ownership and [setup](docs/setup.md) for dependencies and Docker checks.

## Publication and license

The maintainer runs [publication checks](PUBLICATION.md); contributors do not need the private policy. Keep configured Git hooks
enabled. Report a sensitive problem without posting private audio or exploit details in a public issue; ask for a confidential
channel first.

Contributions use the [MIT License](LICENSE).
