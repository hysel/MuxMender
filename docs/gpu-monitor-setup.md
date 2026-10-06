# GPU sharing setup on TrueNAS

Every app release includes a ready-to-run GPU monitor installer at
`deploy/truenas/install_gpu_monitor.py`. Its collector is embedded in the
package, so there is no separate download or Python package installation.

Run the installer once as an administrator on the TrueNAS host:

```sh
sudo python3 /path/to/extracted-package/deploy/truenas/install_gpu_monitor.py --install --group 3005
```

Use your app's group ID. The installer starts the restricted monitor and
registers its TrueNAS Post Init task automatically. Running the installer again
updates its own files and reuses the existing startup task.

Add a read-only Host Path mount from `/var/lib/muxmender-gpu-monitor` to
`/gpu-telemetry`. Set `MUXMENDER_GPU_TELEMETRY=/gpu-telemetry/activity.json`.
Then enable **Yield GPU to other apps** in the dashboard. Its status explains
whether current telemetry is available and whether other GPU work is detected.

The host directory persists across normal reboots, so app updates can validate
the mount even before the monitor starts. The monitor's executable and service
are restored at startup. Following a TrueNAS system upgrade, verify the startup
task and directory; reinstall the bundled helper if the host reset its files.

When upgrading from the older `/run/muxmender-gpu-monitor` mount, run the new
installer first, then change only that mount's Host Path to
`/var/lib/muxmender-gpu-monitor`. Keep its container path `/gpu-telemetry`.

GPU sharing is optional. A new installation can omit this mount and environment
variable and leave sharing off. If telemetry is missing or stale with sharing
enabled, the dashboard reports it and admission waits for current measurements.
Do not create an empty media/output directory to work around a mount error.

The monitor reads GPU activity and process identity on the host. It does not
control other apps, read media, or need the Docker socket. The container retains
its existing permissions. Installation requires an administrator because the
host monitor and startup task run outside the app.
