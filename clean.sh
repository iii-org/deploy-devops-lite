#!/usr/bin/env bash

set -e

echo -e "\e[33mWARNING: This script will remove all data in your directory.\e[0m"
echo -e "\e[33mOnly run this for a fresh install.\e[0m"
echo -e "Press \e[96mCtrl+C\e[0m to cancel, sleep 5 seconds to continue..."
sleep 5

docker compose down -v
rm .initialized
rm environments.json
echo "Done!"
