#!/usr/bin/env bash

set -euo pipefail

# Load common functions
base_dir="$(cd "$(dirname "$0")" && pwd)"
source "$base_dir"/common.sh

# Set project directory
PROJECT_DIR="$(cd "${base_dir}/.." && pwd)"

# Colors for output
# RED='\033[0;31m'
# GREEN='\033[0;32m'
# YELLOW='\033[1;33m'
NC='\033[0m' # No Color

verify_step() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ $1 succeeded${NC}"
        return 0
    else
        echo -e "${RED}❌ $1 failed${NC}"
        return 1
    fi
}

# Function to verify SSH connection
verify_ssh_connection() {
    local user=$1
    local ip=$2
    echo -e "${YELLOW}Verifying SSH connection to $user@$ip...${NC}"
    if ssh -o StrictHostKeyChecking=no -o BatchMode=yes -o ConnectTimeout=5 "$user@$ip" echo "SSH connection successful" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ SSH connection verified${NC}"
        return 0
    else
        echo -e "${RED}❌ SSH connection failed. Please ensure:${NC}"
        echo "  1. The remote machine is accessible"
        echo "  2. SSH key is properly set up"
        echo "  3. The user has proper permissions"
        return 1
    fi
}

# Function to copy files
copy_files() {
    local user=$1
    local ip=$2
    
    echo -e "${YELLOW}Creating remote directory structure...${NC}"
    ssh "$user@$ip" "mkdir -p ~/deploy-devops-lite/docker" || return 1
    verify_step "Create directory structure"

    echo -e "${YELLOW}Copying .env file...${NC}"
    scp "$PROJECT_DIR/.env" "$user@$ip:~/deploy-devops-lite/.env" || return 1
    verify_step "Copy .env file"

    echo -e "${YELLOW}Copying docker compose files...${NC}"
    scp "$PROJECT_DIR/docker/docker-compose.WORKER.yaml" "$user@$ip:~/deploy-devops-lite/docker/" || return 1
    verify_step "Copy docker compose files"
    cat <<'EOF' > /tmp/docker-compose.yaml
include:
  - path: docker/docker-compose.\${MODE:-NONE}.yaml
    project_directory: .

networks:
  default:
    name: iiidevops-lite-network
EOF
    echo -e "${YELLOW}Copying docker compose files...${NC}"
    scp /tmp/docker-compose.yaml "$user@$ip:~/deploy-devops-lite/docker-compose.yaml" || return 1
    verify_step "Copy docker compose files"

    return 0
}

# Function to comment out worker sections
comment_worker_sections() {
    echo -e "${YELLOW}Commenting out worker sections in docker compose files...${NC}"
    
    # Comment out in docker-compose.IP.yaml (lines 97-100)
    awk '
        NR >= 97 && NR <= 100 {
            if ($0 !~ /^[[:space:]]*#/) {
                print "  #" substr($0, 3)
            } else {
                print $0
            }
            next
        }
        { print $0 }
    ' "$PROJECT_DIR/docker/docker-compose.IP.yaml" > "$PROJECT_DIR/docker/docker-compose.IP.yaml.tmp"
    mv "$PROJECT_DIR/docker/docker-compose.IP.yaml.tmp" "$PROJECT_DIR/docker/docker-compose.IP.yaml"
    
    # Comment out in docker-compose.base.yaml (lines 238-246)
    awk '
        NR >= 238 && NR <= 246 {
            if ($0 !~ /^[[:space:]]*#/) {
                print "  #" substr($0, 3)
            } else {
                print $0
            }
            next
        }
        { print $0 }
    ' "$PROJECT_DIR/docker/docker-compose.base.yaml" > "$PROJECT_DIR/docker/docker-compose.base.yaml.tmp"
    mv "$PROJECT_DIR/docker/docker-compose.base.yaml.tmp" "$PROJECT_DIR/docker/docker-compose.base.yaml"
    
    verify_step "Comment out worker sections"
}

# Function to uncomment worker sections
uncomment_worker_sections() {
    echo -e "${YELLOW}Uncommenting worker sections in docker compose files...${NC}"
    
    # Uncomment in docker-compose.IP.yaml (lines 97-100)
    awk '
        NR >= 97 && NR <= 100 {
            if ($0 ~ /^[[:space:]]*#/) {
                print "  " substr($0, 4)
            } else {
                print $0
            }
            next
        }
        { print $0 }
    ' "$PROJECT_DIR/docker/docker-compose.IP.yaml" > "$PROJECT_DIR/docker/docker-compose.IP.yaml.tmp"
    mv "$PROJECT_DIR/docker/docker-compose.IP.yaml.tmp" "$PROJECT_DIR/docker/docker-compose.IP.yaml"
    
    # Uncomment in docker-compose.base.yaml (lines 238-246)
    awk '
        NR >= 238 && NR <= 246 {
            if ($0 ~ /^[[:space:]]*#/) {
                print "  " substr($0, 4)
            } else {
                print $0
            }
            next
        }
        { print $0 }
    ' "$PROJECT_DIR/docker/docker-compose.base.yaml" > "$PROJECT_DIR/docker/docker-compose.base.yaml.tmp"
    mv "$PROJECT_DIR/docker/docker-compose.base.yaml.tmp" "$PROJECT_DIR/docker/docker-compose.base.yaml"
    
    verify_step "Uncomment worker sections"
}

# Function to modify .env file on remote
modify_env() {
    local user=$1
    local ip=$2
    
    echo -e "${YELLOW}Modifying remote .env file...${NC}"
    ssh "$user@$ip" "sed -i 's/MODE=.*/MODE='\''WORKER'\''/g' ~/deploy-devops-lite/.env" || return 1
    verify_step "Modify .env file"

    # Verify the change
    echo -e "${YELLOW}Verifying MODE setting in .env...${NC}"
    ssh "$user@$ip" "grep '^MODE=' ~/deploy-devops-lite/.env" | grep -q "WORKER"
    verify_step "Verify MODE setting"

    return 0
}

# Main script
main() {
    echo "III DevOps Worker Setup"
    echo "======================="

    # Ask user for worker setup type
    echo -e "${YELLOW}Choose worker setup type:${NC}"
    echo "1. Remote worker (setup on a different machine)"
    echo "2. Local worker (setup on this machine)"
    read -p "Enter your choice (1/2): " setup_choice

    case $setup_choice in
        1)
            # Remote worker setup
            echo -e "\n${YELLOW}Setting up remote worker...${NC}"

            # Ask for remote user and IP
            read -p "Enter remote user: " remote_user
            read -p "Enter remote IP: " remote_ip

            # Verify SSH connection
            if ! verify_ssh_connection "$remote_user" "$remote_ip"; then
                exit 1
            fi

            # Copy necessary files
            if ! copy_files "$remote_user" "$remote_ip"; then
                echo -e "${RED}Failed to copy files${NC}"
                exit 1
            fi

            # Modify .env file
            if ! modify_env "$remote_user" "$remote_ip"; then
                echo -e "${RED}Failed to modify .env file${NC}"
                exit 1
            fi

            # Comment out worker sections in docker compose files
            if ! comment_worker_sections; then
                echo -e "${RED}Failed to comment out worker sections${NC}"
                exit 1
            fi

            echo -e "\n${GREEN}Remote worker setup completed successfully!${NC}"
            echo -e "Next steps:"
            echo -e "1. SSH into the worker: ${YELLOW}ssh $remote_user@$remote_ip${NC}"
            echo -e "2. Navigate to deploy-devops-lite: ${YELLOW}cd ~/deploy-devops-lite${NC}"
            echo -e "3. Start the worker: ${YELLOW}docker-compose up -d${NC}"
            echo -e "4. Check the worker logs: ${YELLOW}docker-compose logs -f${NC}"
            ;;
        2)
            # Local worker setup
            echo -e "\n${YELLOW}Setting up local worker...${NC}"
            
            # Uncomment worker sections in docker compose files
            if ! uncomment_worker_sections; then
                echo -e "${RED}Failed to uncomment worker sections${NC}"
                exit 1
            fi
            
            echo -e "${GREEN}Local worker setup completed!${NC}"
            echo -e "The worker service will be started with other services."
            ;;
        *)
            echo -e "${RED}Invalid choice. Please select 1 for remote worker or 2 for local worker.${NC}"
            exit 1
            ;;
    esac
}

main "$@"