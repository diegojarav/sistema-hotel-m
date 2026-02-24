#!/bin/bash
# ==========================================
# Hotel Munich PMS - Linux Service Control
# ==========================================
#
# Manages the 3 systemd services:
#   hotel-backend  (FastAPI on :8000)
#   hotel-pc       (Streamlit on :8501)
#   hotel-mobile   (Next.js on :3000)
#
# Usage:
#   bash scripts/service_control_linux.sh status
#   bash scripts/service_control_linux.sh start
#   bash scripts/service_control_linux.sh stop
#   bash scripts/service_control_linux.sh restart
#   bash scripts/service_control_linux.sh logs [service]
#
# ==========================================

SERVICES="hotel-backend hotel-pc hotel-mobile"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

case "${1:-}" in

    status)
        echo ""
        echo -e "${BLUE}  HOTEL MUNICH PMS — SERVICE STATUS${NC}"
        echo ""
        for svc in ${SERVICES}; do
            STATUS=$(systemctl is-active ${svc} 2>/dev/null || echo "not-found")
            case ${STATUS} in
                active)   echo -e "  ${GREEN}[RUNNING]${NC}  ${svc}" ;;
                inactive) echo -e "  ${YELLOW}[STOPPED]${NC}  ${svc}" ;;
                failed)   echo -e "  ${RED}[FAILED]${NC}   ${svc}" ;;
                *)        echo -e "  ${RED}[??????]${NC}   ${svc} (${STATUS})" ;;
            esac
        done
        echo ""

        # Health check
        HEALTH=$(curl -s --connect-timeout 3 http://localhost:8000/health 2>/dev/null)
        if [ -n "${HEALTH}" ]; then
            echo -e "  ${BLUE}Health:${NC} ${HEALTH}"
        else
            echo -e "  ${YELLOW}Health:${NC} Backend not responding"
        fi
        echo ""
        ;;

    start)
        echo -e "${BLUE}Starting all services...${NC}"
        sudo systemctl start hotel-backend
        sleep 3
        sudo systemctl start hotel-pc hotel-mobile
        sleep 2
        echo -e "${GREEN}All services started.${NC}"
        $0 status
        ;;

    stop)
        echo -e "${YELLOW}Stopping all services...${NC}"
        for svc in ${SERVICES}; do
            sudo systemctl stop ${svc}
        done
        echo -e "${GREEN}All services stopped.${NC}"
        ;;

    restart)
        echo -e "${BLUE}Restarting all services...${NC}"
        for svc in ${SERVICES}; do
            sudo systemctl stop ${svc}
        done
        sleep 2
        sudo systemctl start hotel-backend
        sleep 3
        sudo systemctl start hotel-pc hotel-mobile
        sleep 2
        echo -e "${GREEN}All services restarted.${NC}"
        $0 status
        ;;

    restart-backend)
        echo -e "${BLUE}Restarting backend...${NC}"
        sudo systemctl restart hotel-backend
        sleep 3
        $0 status
        ;;

    restart-pc)
        echo -e "${BLUE}Restarting PC frontend...${NC}"
        sudo systemctl restart hotel-pc
        sleep 2
        $0 status
        ;;

    restart-mobile)
        echo -e "${BLUE}Restarting mobile frontend...${NC}"
        sudo systemctl restart hotel-mobile
        sleep 2
        $0 status
        ;;

    logs)
        SERVICE="${2:-}"
        if [ -z "${SERVICE}" ]; then
            echo -e "${BLUE}Following all service logs (Ctrl+C to stop)...${NC}"
            sudo journalctl -u hotel-backend -u hotel-pc -u hotel-mobile -f --no-hostname
        else
            echo -e "${BLUE}Following ${SERVICE} logs (Ctrl+C to stop)...${NC}"
            sudo journalctl -u "${SERVICE}" -f --no-hostname
        fi
        ;;

    *)
        echo ""
        echo -e "${BLUE}Hotel Munich PMS - Service Control${NC}"
        echo ""
        echo "Usage: $0 <command>"
        echo ""
        echo "Commands:"
        echo "  status            Show status of all services"
        echo "  start             Start all services"
        echo "  stop              Stop all services"
        echo "  restart           Restart all services"
        echo "  restart-backend   Restart only the backend"
        echo "  restart-pc        Restart only the PC frontend"
        echo "  restart-mobile    Restart only the mobile frontend"
        echo "  logs [service]    Follow service logs (all or specific)"
        echo ""
        ;;

esac
