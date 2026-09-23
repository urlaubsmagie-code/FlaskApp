# Podman migration - 2026-09-15

Services:
- n8n: http://localhost:5678 (container `umi-n8n`, version 2.3.6).
- WAHA: http://localhost:3002/dashboard (container `umi-waha`, WEBJS).
- WAHA credentials: `../waha/.env`, not committed.

The Windows scheduled task `UMI Podman Services` starts the services at this
user's logon with elevated privileges. This is logon startup, not unattended
startup before someone signs in.

Start existing services manually from an administrator PowerShell:

```powershell
& .\podman\start-services.ps1
```

Podman Desktop displays these containers in its Containers page.
Windows port forwarding maps port 5678 to n8n and local-only port 3002 to WAHA.
The startup script refreshes the destination after the WSL machine IP changes.
If the machine is restarted manually, run the startup script again.
Docker Desktop is not needed to run them. Do not start the old n8n Docker
container while Podman n8n is running: both would run the same schedules.

Storage:
- Current n8n data: `D:\UMI-containers\n8n\data`.
- n8n environment: `D:\UMI-containers\n8n\.env`.
- Review workflow files retain their existing host path `C:\n8n_Docker\Files`
  and container path `/home/node/.n8n-files` for compatibility with Flask.
- WAHA sessions/media: Podman named volumes `umi-waha-sessions`, `umi-waha-media`.
- Verified original Docker disk backup and n8n data/files backup:
  `D:\UMI-migration-backups\20260915-135851`.
- Original n8n data remains at `C:\n8n_Docker\n8n_data`.

Migration checks: n8n database integrity passed; 6 workflows and 8 credentials
were preserved, all 8 credentials could be decrypted, and 5 active workflows
were restored. n8n readiness/editor and the WAHA dashboard/API returned HTTP
200; WAHA rejected an unauthenticated API request with HTTP 401. Workflow
business actions were not manually triggered as part of verification.

WAHA is infrastructure only at this stage: no phone is paired, and the Flask
WAHA adapter has not been implemented. The existing Baileys bridge remains UMI's
WhatsApp connection. Do not pair the business number until cutover is prepared.

Backup n8n's entire data directory including its `config` encryption key;
workflow JSON exports alone do not preserve working credentials.
Do not remove the Podman machine or volumes without backing them up.
