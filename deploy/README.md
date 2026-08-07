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

## Why not Workers, and why not Containers either

**Workers** have no persistent filesystem, a 128 MB isolate limit against the ~200 MB this
settles at, and no numpy — the FFT convolution and the vectorized binary search over
20,000-participant fields would need porting to JS or WASM. That is a rewrite of the most
carefully validated code here to fit a runtime that does not want it.

**Containers** would genuinely run this: arbitrary Docker images at up to 4 vCPU / 12 GiB /
20 GB disk, so the app and numpy work unchanged. Two things still make it the wrong shape:

- **Container disk is ephemeral.** Cloudflare's own docs say so plainly, and instances sleep
  after an idle timeout. The 600 MB cache is the entire performance design; losing it means
  re-pulling ~16 GB at one request per second, which takes hours. Surviving that needs the
  cache baked into the image (600 MB image, rebuilt and redeployed to refresh) or moved to R2
  with the storage layer rewritten to read objects instead of files.
- **No free tier, and it is billed for wall-clock time awake.** Containers need the $5/month
  Workers Paid plan; at ~100 visitors an hour the instance is effectively never idle, so
  memory and vCPU land somewhere around $10-15/month all in. A small VPS running the tunnel
  is cheaper and keeps a real disk.

Containers are the right answer if you ever want this to scale out or stop owning a box. For
one instance serving a hundred people an hour, a persistent disk is worth more than elasticity.

## Checking it worked

```bash
curl -s https://vrating.yourdomain.com/healthz
```

`warm: true` means the prewarm finished and requests are being served from disk.
