#!/bin/bash
# Script de diagnóstico para MyFoil
# Verifica endpoints API, WebSocket e problemas comuns

echo "=========================================="
echo "MyFoil Diagnostics Tool"
echo "=========================================="
echo ""

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# URL padrão (modifique se necessário)
BASE_URL="${1:-http://localhost:8465}"

echo "Testing against: $BASE_URL"
echo ""

# Função para teste de endpoint
test_endpoint() {
    local name="$1"
    local url="$2"
    local auth="$3"

    printf "%-40s " "$name..."
    
    if [ -n "$auth" ]; then
        response=$(curl -s -w "\n%{http_code}" "$url" -H "Authorization: $auth" 2>/dev/null)
    else
        response=$(curl -s -w "\n%{http_code}" "$url" 2>/dev/null)
    fi

    if [ $? -ne 0 ]; then
        echo -e "${RED}FAILED (Connection refused)${NC}"
        return 1
    fi

    body=$(echo "$response" | head -n -1)
    status=$(echo "$response" | tail -n 1)

    if [ "$status" -eq 200 ]; then
        echo -e "${GREEN}OK (200)${NC}"
        return 0
    elif [ "$status" -eq 401 ]; then
        echo -e "${YELLOW}401 Unauthorized${NC}"
        return 2
    elif [ "$status" -eq 404 ]; then
        echo -e "${YELLOW}404 Not Found${NC}"
        return 3
    else
        echo -e "${RED}FAILED ($status)${NC}"
        echo "  Error: $body" | head -n 1
        return 4
    fi
}

echo "1. Testing Basic Endpoints"
echo "---"
test_endpoint "Home Page" "$BASE_URL/"
test_endpoint "Static CSS" "$BASE_URL/static/css/bulma.min.css"
test_endpoint "Static JS" "$BASE_URL/static/js/base.js"
echo ""

echo "2. Testing API Endpoints"
echo "---"
# Note: These require authentication
test_endpoint "Legacy Library" "$BASE_URL/api/library?page=1&per_page=10"
test_endpoint "Paged Library" "$BASE_URL/api/library/paged?page=1&per_page=10"
test_endpoint "Health Check" "$BASE_URL/api/health"
echo ""

echo "3. Checking WebSocket/Socket.IO"
echo "---"
printf "%-40s " "Socket.IO endpoint..."
response=$(curl -s -I "$BASE_URL/socket.io/" 2>/dev/null | head -n 1)
if echo "$response" | grep -q "200\|400"; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${YELLOW}Not available or configured${NC}"
    echo "  Response: $response"
fi
echo ""

echo "4. Database Connection Check"
echo "---"
printf "%-40s " "Database response time..."
start=$(date +%s%3N)
curl -s "$BASE_URL/api/health" > /dev/null 2>&1
end=$(date +%s%3N)
duration=$((end - start))

if [ $duration -lt 1000 ]; then
    echo -e "${GREEN}${duration}ms${NC}"
elif [ $duration -lt 3000 ]; then
    echo -e "${YELLOW}${duration}ms (slower than expected)${NC}"
else
    echo -e "${RED}${duration}ms (very slow, check DB)${NC}"
fi
echo ""

echo "5. Configuration Check"
echo "---"
printf "%-40s " "Check for admin users..."
# Verifica se há usuário admin configurado
# (Requer acesso ao banco de dados)
echo -e "${YELLOW}Cannot check remotely${NC}"
echo "  Run: python3 -c \"from db import User; print(User.query.filter_by(admin_access=True).count())\""
echo "  on the server to check"
echo ""

echo "=========================================="
echo "Diagnostics Complete"
echo "=========================================="
echo ""
echo "Common Issues:"
echo ""
echo "1. ERR_CONNECTION_REFUSED:"
echo "   - Check if MyFoil is running: ps aux | grep python | grep app.py"
echo "   - Check if port 8465 is free: netstat -tlnp | grep 8465"
echo "   - Check firewall rules"
echo ""
echo "2. 401 Unauthorized:"
echo "   - Create admin user via Settings page"
echo "   - Check user.shop_access = True"
echo ""
echo "3. 500 Internal Server Error:"
echo "   - Check application logs: tail -f /path/to/MyFoil/logs/app.log"
echo "   - Check database connection"
echo "   - Check for missing files/dependencies"
echo ""
echo "4. WebSocket Errors:"
echo "   - Check Redis is running (for Socket.IO support)"
echo "   - Check REDIS_URL in environment variables"
echo "   - Socket.IO can still work without Redis (limited to single server)"
echo ""
echo "For detailed logs:"
echo "  SSH into the server and run:"
echo "    tail -100 /path/to/MyFoil/logs/app.log"
echo "    grep -i error /path/to/MyFoil/logs/app.log | tail -50"
echo ""
