#!/bin/bash

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "Error: Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Script functionality
case "$1" in
    start)
        echo "Starting MongoDB container..."
        docker-compose up -d
        echo "MongoDB started on port: 27017"
        ;;
    stop)
        echo "Stopping MongoDB container..."
        docker-compose down
        echo "MongoDB stopped"
        ;;
    restart)
        echo "Restarting MongoDB container..."
        docker-compose restart
        echo "MongoDB restarted"
        ;;
    status)
        echo "MongoDB container status:"
        docker-compose ps
        ;;
    logs)
        echo "Viewing MongoDB logs:"
        docker-compose logs -f mongodb
        ;;
    shell)
        echo "Entering MongoDB Shell:"
        docker-compose exec mongodb mongosh
        ;;
    backup)
        timestamp=$(date +%Y%m%d_%H%M%S)
        backup_dir="./backups"
        mkdir -p $backup_dir
        echo "Backing up MongoDB data..."
        docker-compose exec -T mongodb mongodump --archive > "$backup_dir/mongodb_backup_$timestamp.archive"
        echo "Backup completed: $backup_dir/mongodb_backup_$timestamp.archive"
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs|shell|backup}"
        echo "  start   - Start MongoDB container"
        echo "  stop    - Stop MongoDB container"
        echo "  restart - Restart MongoDB container"
        echo "  status  - View MongoDB container status"
        echo "  logs    - View MongoDB logs"
        echo "  shell   - Enter MongoDB Shell"
        echo "  backup  - Backup MongoDB data"
        exit 1
        ;;
esac

exit 0 