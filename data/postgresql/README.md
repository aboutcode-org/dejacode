# Generate `initdb.sql.gz` (shareable initial seed)

This guide produces a compressed SQL dump (`initdb.sql.gz`) that Postgres loads
automatically on first startup (via `/docker-entrypoint-initdb.d/`). It uses plain
`docker` commands only, with no extra compose file, and never touches your local stack.

## Prerequisites: Dump the reference data from server

Run against the reference instance:

```sh
docker compose -f /opt/dejacode/docker-compose.yml exec web ./manage.py dumpinitdata nexB > initdb_dataset.json
```

## Steps

Run the following on your local DejaCode checkout.

### 1. Fetch the initdb_dataset.json file from the server

### 2. Build web image from the project root

```sh
cd dejacode
docker build -t dejacode-web .
```

### 3. Create a network and start the empty database

The container has no named volume (ephemeral) and is reachable as `db` on the network.

```sh
docker network create dejacode-seed-net

docker run -d \
  --name dejacode-seed-db \
  --network dejacode-seed-net \
  --network-alias db \
  --env-file docker.env \
  --shm-size=1g \
  docker.io/library/postgres:16.13
```

### 4. Apply migrations on the fresh database

```sh
docker run --rm \
  --network dejacode-seed-net \
  --env-file docker.env \
  -v "$(pwd)/.env:/opt/dejacode/.env" \
  -v /etc/dejacode/:/etc/dejacode/ \
  dejacode-web ./manage.py migrate
```

### 5. Load the data from stdin

`loaddata` reads the JSON from standard input, so there is no file to mount.
The `-i` flag keeps stdin open for the redirection.

```sh
docker run --rm -i \
  --network dejacode-seed-net \
  --env-file docker.env \
  -v "$(pwd)/.env:/opt/dejacode/.env" \
  -v /etc/dejacode/:/etc/dejacode/ \
  dejacode-web ./manage.py loaddata --format=json - < initdb_dataset.json
```

This will take over 10 minutes to run.

### 6. Inspect and tweak

```sh
docker run --rm -it \
  --network dejacode-seed-net \
  --env-file docker.env \
  -v "$(pwd)/.env:/opt/dejacode/.env" \
  -v /etc/dejacode/:/etc/dejacode/ \
  dejacode-web ./manage.py shell
```

```python
dataspace = Dataspace.objects.get_reference()
values = {
    "homepage_url": "",
    "contact_info": "",
    "notes": "",
    "logo_url": "",
    "address": "",
    "open_source_information_url": "",
    "open_source_download_url": "",
    # "home_page_announcements": "",
    "show_license_profile_in_license_list_view": True,
    "show_spdx_short_identifier_in_license_list_view": True,
    "show_usage_policy_in_user_views": True,
    "show_type_in_component_list_view": False,
    "hide_empty_fields_in_component_details_view": True,
    "set_usage_policy_on_new_component_from_licenses": True,
    "enable_package_scanning": True,
    "update_packages_from_scan": True,
    "enable_purldb_access": True,
    "enable_vulnerablecodedb_access": True,
    "vulnerabilities_updated_at": None,
}
Dataspace.objects.filter(id=dataspace.id).update(**values)
dataspace.set_configuration("homepage_layout", None)
dataspace.set_configuration("vulnerablecode_url", "https://public.vulnerablecode.io/")
dataspace.set_configuration("purldb_url", "https://public.purldb.io/")
```

### 7. Extract the compressed SQL dump

`pg_dump` runs inside the container (Postgres 16.13). `--no-owner --no-privileges`
makes the dump replayable even if another deployment uses a different `POSTGRES_USER`.

```sh
docker exec dejacode-seed-db \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges' \
  | gzip > data/postgresql/initdb.sql.gz
```

### 8. Verify the seed

The `initdb.d` scripts run **only on a fresh db volume**. To test the artifact without
breaking your local setup, start the main stack with a throwaway project name and a new
volume:

```sh
docker compose -p dejacode-check up -d db
# check the data is present, then:
docker compose -p dejacode-check down -v
```

### 9. Tear everything down

```sh
docker rm -fv dejacode-seed-db
docker network rm dejacode-seed-net
```

`-v` removes the anonymous volume created by the Postgres image. Your local `dejacode`
stack was never touched.
