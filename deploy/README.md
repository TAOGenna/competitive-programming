# Deploying

Two shapes, depending on whether you want to run the box yourself.

## Cloudflare Tunnel (recommended if you have a Cloudflare account)

Your domain, TLS, and DDoS protection at the edge; the machine needs no public IP, no open
inbound ports and no certificate. Works from a VPS or from a machine at home.

```bash
# on the box
git clone git@github.com:TAOGenna/vrating.git /srv/vrating && cd /srv/vrating
pip install -r requirements.txt
python3 -m vrating.sources.prewarm            # ~35 min, ~16 GB down, ~600 MB kept
sudo cp deploy/vrating.service /etc/systemd/system/ && sudo systemctl enable --now vrating

# the tunnel
cloudflared tunnel login
cloudflared tunnel create vrating
cloudflared tunnel route dns vrating vrating.yourdomain.com
sudo cp deploy/cloudflared.yml /etc/cloudflared/config.yml   # edit the hostname
sudo cloudflared service install
```

`deploy/nginx.conf` is then unnecessary — skip it.

### The one Cloudflare-specific hazard

Cloudflare returns **error 524 if the origin sends nothing for 100 seconds**. A cold cache can
spend minutes fetching standings before it has anything to report, which would look like the
site being broken. The server emits an SSE keepalive every 20 s during those phases, and sends
`X-Accel-Buffering: no` so nothing between here and the browser holds the stream back.

Prewarm is still what makes this a non-issue: warm, nothing takes longer than a few seconds.

## Plain nginx

Use `deploy/nginx.conf` instead of the tunnel. It carries the same requirement in nginx's own
terms: `proxy_buffering off`, without which nginx holds the entire reply until it finishes and
a working page looks frozen.

## Why not Cloudflare Workers

Workers have no persistent filesystem, and the 600 MB contest cache is the thing that makes
this fast; it would have to move to R2, one object per contest. The 128 MB isolate limit is
below the ~200 MB the server settles at. And the rating maths — an FFT convolution and a
vectorized binary search over 20,000-participant fields — is numpy, so it would need porting
to JS or WASM. That is a rewrite of the most carefully validated code in the project to fit a
runtime that does not want it. Tunnel keeps the Python and still gives you the Cloudflare edge.

## Checking it worked

```bash
curl -s https://vrating.yourdomain.com/healthz
```

`warm: true` means the prewarm finished and requests are being served from disk.
