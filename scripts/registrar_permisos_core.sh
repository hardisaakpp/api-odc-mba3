#!/bin/bash
# Script para registrar permisos del módulo MBA3 Consultas en el Core
# Uso: ./registrar_permisos_core.sh http://localhost:5000 "tu-token-jwt" "Ventas"

CORE_URL="${1:-http://localhost:5000}"
ADMIN_TOKEN="${2}"
ROLE_NAME="${3:-Ventas}"

if [ -z "$ADMIN_TOKEN" ]; then
    echo "❌ Error: Debes proporcionar un token de administrador"
    echo "Uso: $0 <core-url> <admin-token> [role-name]"
    exit 1
fi

echo "========================================"
echo "Registro de Permisos MBA3 Consultas"
echo "========================================"
echo ""

# Colores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Función para registrar permiso
registrar_permiso() {
    local key=$1
    local description=$2
    local module=$3
    
    echo -e "${GREEN}Registrando: $key${NC}"
    
    response=$(curl -s -w "\n%{http_code}" -X POST "$CORE_URL/api/permissions" \
        -H "Authorization: Bearer $ADMIN_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{
            \"key\": \"$key\",
            \"description\": \"$description\",
            \"module\": \"$module\"
        }")
    
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')
    
    if [ "$http_code" -eq 200 ] || [ "$http_code" -eq 201 ]; then
        permission_id=$(echo "$body" | grep -o '"id":[0-9]*' | grep -o '[0-9]*' | head -1)
        echo -e "  ${GREEN}✅ Permiso registrado con ID: $permission_id${NC}"
        echo "$permission_id"
    elif [ "$http_code" -eq 409 ]; then
        echo -e "  ${YELLOW}⚠️  Permiso ya existe${NC}"
        # Intentar obtener el ID del permiso existente
        get_response=$(curl -s "$CORE_URL/api/permissions" \
            -H "Authorization: Bearer $ADMIN_TOKEN")
        permission_id=$(echo "$get_response" | grep -o "\"key\":\"$key\".*\"id\":[0-9]*" | grep -o '"id":[0-9]*' | grep -o '[0-9]*' | head -1)
        if [ -n "$permission_id" ]; then
            echo -e "  ${GREEN}✅ Permiso encontrado con ID: $permission_id${NC}"
            echo "$permission_id"
        else
            echo -e "  ${RED}❌ No se pudo obtener ID del permiso existente${NC}"
            echo ""
        fi
    else
        echo -e "  ${RED}❌ Error al registrar permiso (HTTP $http_code)${NC}"
        echo "$body"
        echo ""
    fi
}

# Función para asignar permiso a rol
asignar_permiso() {
    local permission_id=$1
    
    echo -e "${GREEN}Asignando permiso ID: $permission_id${NC}"
    
    response=$(curl -s -w "\n%{http_code}" -X POST "$CORE_URL/api/permissions/assign" \
        -H "Authorization: Bearer $ADMIN_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{
            \"roleName\": \"$ROLE_NAME\",
            \"permissionId\": $permission_id
        }")
    
    http_code=$(echo "$response" | tail -n1)
    
    if [ "$http_code" -eq 200 ] || [ "$http_code" -eq 201 ]; then
        echo -e "  ${GREEN}✅ Permiso asignado exitosamente${NC}"
    elif [ "$http_code" -eq 409 ]; then
        echo -e "  ${YELLOW}⚠️  Permiso ya está asignado a este rol${NC}"
    else
        echo -e "  ${RED}❌ Error al asignar permiso (HTTP $http_code)${NC}"
    fi
    echo ""
}

# Paso 1: Registrar permisos
echo -e "${YELLOW}Paso 1: Registrando permisos...${NC}"
echo ""

PERMISSION_IDS=()

# Permiso 1: Ver facturas
id1=$(registrar_permiso "mba3-consultas.facturas.view" "Ver facturas MBA3" "mba3-consultas")
if [ -n "$id1" ]; then
    PERMISSION_IDS+=("$id1")
fi
echo ""

# Permiso 2: Ejecutar procesos
id2=$(registrar_permiso "mba3-consultas.proceso.execute" "Ejecutar procesos MBA3 (consultar, migrar, procesar OC, integrar SAP)" "mba3-consultas")
if [ -n "$id2" ]; then
    PERMISSION_IDS+=("$id2")
fi
echo ""

# Permiso 3: Ver órdenes de compra
id3=$(registrar_permiso "mba3-consultas.ordenes-compra.view" "Ver órdenes de compra" "mba3-consultas")
if [ -n "$id3" ]; then
    PERMISSION_IDS+=("$id3")
fi
echo ""

# Paso 2: Asignar permisos a rol
echo -e "${YELLOW}Paso 2: Asignando permisos al rol '$ROLE_NAME'...${NC}"
echo ""

for permission_id in "${PERMISSION_IDS[@]}"; do
    asignar_permiso "$permission_id"
done

echo "========================================"
echo -e "${GREEN}✅ Proceso completado${NC}"
echo "========================================"
echo ""
echo -e "${YELLOW}⚠️  IMPORTANTE: Los usuarios deben hacer login nuevamente${NC}"
echo -e "${YELLOW}   para obtener tokens con los nuevos permisos.${NC}"
echo ""































