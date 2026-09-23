# WAHA staging setup

Current Windows installation runs in **Podman**, migrated on 2026-09-15.
See [Podman operation and backups](../podman/README.md). Keep Docker Desktop
stopped; the Compose commands below are for a separate future Docker deployment.

The supplied Compose project is separate from n8n and the existing Baileys bridge.
Dashboard: http://localhost:3002/dashboard

Credentials are generated in `.env` (ignored by Git):
- Login: `WAHA_DASHBOARD_USERNAME` and `WAHA_DASHBOARD_PASSWORD`.
- Dashboard server URL: `http://localhost:3002`.
- Dashboard API key: `WAHA_API_KEY`.

From this directory:

```powershell
docker compose up -d
docker compose ps
docker compose stop
```

Docker Desktop must be running. `unless-stopped` restarts the container when
Docker restarts unless you explicitly stopped the container.

Sessions and media use named Docker volumes. Back these up before migration.
Do not use `docker compose down -v`: it deletes persistent data.
Media is retained until explicitly cleaned up; monitor disk usage.

This setup does not yet route WAHA messages into UMI. UMI still uses Baileys.
Use a test number for initial pairing. Business-number cutover should follow
the Flask adapter implementation and verification, with the old bridge stopped.
Never copy Baileys auth files into WAHA: pair through WAHA's QR flow.

Future WAHA webhooks to Flask running on this Windows host need a host address
reachable from the container (Podman provides `host.containers.internal`).
Verify reachability during adapter setup; container-local `localhost` is WAHA itself.
Do not point WAHA at the existing webhook until its event format is adapted.

Sources:
- https://waha.devlike.pro/docs/overview/quick-start/
- https://waha.devlike.pro/docs/how-to/security/
- https://waha.devlike.pro/docs/how-to/storages/
