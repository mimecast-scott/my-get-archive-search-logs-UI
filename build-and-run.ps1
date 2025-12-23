docker build -t ghcr.io/mimecast-scott/mimecast-searchlogs:latest . 
docker run --env-file .env -v mimecast_searchlogs_data:/data ghcr.io/mimecast-scott/mimecast-searchlogs:latest


