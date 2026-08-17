# Security policy

## Supported version

Security fixes are currently provided for the latest OpenDeskNode release.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting feature on the OpenDeskNode
repository. Do not include API keys, Wi-Fi credentials, private network dumps,
or other secrets in a public issue.

## Deployment boundary

OpenDeskNode v0.1.0's Stock Gateway has no authentication. Run it only on a
trusted LAN behind your normal firewall. Do not forward its port to the public
Internet. Keep `.env`, SQLite databases, and logs outside Git.
