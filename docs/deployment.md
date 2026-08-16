# Deployment

## Python service

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp config.example.toml config.toml
powersite-sentinel --config config.toml serve
```

Open `http://127.0.0.1:8090/`.

MorningstarModbusAPI should normally run on the same edge computer at `http://127.0.0.1:8080`.

## Docker

```bash
docker build -t powersite-sentinel .
docker run --rm --network host \
  -v "$PWD/data:/data" \
  -e SENTINEL_MORNINGSTAR_URL=http://127.0.0.1:8080 \
  powersite-sentinel
```

Host networking is convenient for a Linux edge appliance where the upstream API binds to loopback. A production
installation can instead place both services behind one reverse proxy/network namespace.

## Systemd

`deploy/systemd/powersite-sentinel.service` is a hardened starting point. Create a dedicated service account, place
configuration in `/etc/powersite-sentinel.toml`, and give the service write access only to its incident database
location.
