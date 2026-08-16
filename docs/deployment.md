# Deployment

## Python service

Start MorningstarModbusAPI in combined watcher/API mode first:

```bash
morningstar-modbus --config /path/to/morningstar-config.toml run
```

Confirm both the API health route and system inventory are reachable:

```bash
curl --fail http://127.0.0.1:8080/health
curl --fail http://127.0.0.1:8080/v1/systems
```

Then start Sentinel:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp config.example.toml config.toml
powersite-sentinel --config config.toml serve
```

Open `http://127.0.0.1:8090/`.

MorningstarModbusAPI should normally run on the same edge computer at `http://127.0.0.1:8080`. Sentinel retries
connection-level failures with bounded asynchronous backoff. Once at least one successful site assessment has been
cached, a brief upstream restart is shown as stale last-known-good data rather than immediately clearing the site
view.

If Sentinel still reports `All connection attempts failed`, the failure is below the `/v1/systems` route: verify that
the Morningstar API process is actually listening on the URL configured by `SENTINEL_MORNINGSTAR_URL`.

## Docker

```bash
docker build -t powersite-sentinel .
docker run --rm --network host \
  -v "$PWD/data:/data" \
  -e SENTINEL_MORNINGSTAR_URL=http://127.0.0.1:8080 \
  powersite-sentinel
```

Host networking is important on a Linux edge appliance when MorningstarModbusAPI binds to host loopback. Without
`--network host`, `127.0.0.1` refers to the Sentinel container itself rather than the host API process. A production
installation can instead place both services on the same container network and configure
`SENTINEL_MORNINGSTAR_URL` with the Morningstar API service name.

## Systemd

`deploy/systemd/powersite-sentinel.service` is a hardened starting point. It orders Sentinel after and weakly wants a
`morningstar-modbus-api.service` unit when one is installed, while still allowing Sentinel to expose its own health and
incident endpoints if the upstream unit is temporarily unavailable. Create a dedicated service account, place
configuration in `/etc/powersite-sentinel.toml`, and give the service write access only to its incident database
location.
