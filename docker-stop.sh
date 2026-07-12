#!/bin/bash
# Script to stop the IGEdge bot

set -e

echo "=========================================="
echo "  Stopping IGEdge Trading Bot"
echo "=========================================="

docker compose stop

echo ""
echo "✓ Bot stopped successfully!"
echo ""
echo "To start again: ./docker-start.sh"
echo "To remove container: docker compose down"
