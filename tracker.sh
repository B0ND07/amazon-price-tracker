#!/bin/bash
# Price Tracker Management Script

case "$1" in
    start)
        echo "Starting price tracker..."
        cd /root/amazon-price-tracker
        nohup python3 main.py > price_tracker.log 2>&1 &
        echo "Price tracker started. PID: $!"
        echo "View logs: tail -f /root/amazon-price-tracker/price_tracker.log"
        ;;
    stop)
        echo "Stopping price tracker..."
        pkill -f "python3 main.py"
        echo "Price tracker stopped."
        ;;
    restart)
        echo "Restarting price tracker..."
        pkill -f "python3 main.py"
        sleep 2
        cd /root/amazon-price-tracker
        nohup python3 main.py > price_tracker.log 2>&1 &
        echo "Price tracker restarted. PID: $!"
        ;;
    status)
        echo "Price tracker status:"
        ps aux | grep "python3 main.py" | grep -v grep || echo "Not running"
        ;;
    logs)
        tail -f /root/amazon-price-tracker/price_tracker.log
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs}"
        exit 1
        ;;
esac
