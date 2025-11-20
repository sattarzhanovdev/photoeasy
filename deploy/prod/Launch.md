# Install docker

```bash
apt install docker.io

DOCKER_CONFIG=${DOCKER_CONFIG:-$HOME/.docker}
mkdir -p $DOCKER_CONFIG/cli-plugins
curl -SL https://github.com/docker/compose/releases/download/v2.40.3/docker-compose-linux-x86_64 -o $DOCKER_CONFIG/cli-plugins/docker-compose

chmod +x $DOCKER_CONFIG/cli-plugins/docker-compose
```

# Copy certs
```bash
ssh root@45.144.178.219
mkdir -p /etc/letsencrypt/live/photoeasy.duckdns.org/
rsync -r /mnt/c/Users/sasha/Documents/Projects/photoeasy/deploy/prod/fullchain.pem root@45.144.178.219:/etc/letsencrypt/live/photoeasy.duckdns.org/fullchain.pem
rsync -r /mnt/c/Users/sasha/Documents/Projects/photoeasy/deploy/prod/privkey.pem root@45.144.178.219:/etc/letsencrypt/live/photoeasy.duckdns.org/privkey.pem
```
