"""Refresh Windows forwarding for this installation's two Podman services."""
import json
import subprocess

result = subprocess.run(['wsl', '-d', 'podman-machine-default', '--',
                         'ip', '-j', '-4', 'addr', 'show', 'eth0'],
                        capture_output=True, check=True)
address = json.loads(result.stdout)[0]['addr_info'][0]['local']
for port, listen in ((5678, '0.0.0.0'), (3002, '127.0.0.1')):
    subprocess.run(['netsh', 'interface', 'portproxy', 'add', 'v4tov4',
                    f'listenaddress={listen}', f'listenport={port}',
                    f'connectaddress={address}', f'connectport={port}'], check=True)
print('Forwarding configured for n8n and WAHA:', address)
