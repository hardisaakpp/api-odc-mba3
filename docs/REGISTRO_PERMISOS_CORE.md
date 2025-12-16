# Registro de Permisos en el Core

Este documento contiene los comandos necesarios para registrar todos los permisos del módulo MBA3 Consultas en el Core.

## 📋 Permisos Requeridos

El módulo requiere **3 permisos únicos**:

1. **`mba3-consultas.facturas.view`** - Ver facturas
2. **`mba3-consultas.proceso.execute`** - Ejecutar procesos (consultar, migrar, procesar, integrar)
3. **`mba3-consultas.ordenes-compra.view`** - Ver órdenes de compra

## 🔧 Pasos para Registrar Permisos

### Paso 1: Obtener Token de Administrador

Primero, necesitas obtener un token JWT de un usuario administrador:

```http
POST http://localhost:5000/api/auth/login
Content-Type: application/json

{
  "username": "admin",
  "password": "tu-password"
}
```

Guarda el token de la respuesta para usarlo en los siguientes pasos.

### Paso 2: Registrar Permisos

Ejecuta estos 3 comandos para registrar los permisos:

#### Permiso 1: Ver Facturas

```http
POST http://localhost:5000/api/permissions
Authorization: Bearer <tu-admin-token>
Content-Type: application/json

{
  "key": "mba3-consultas.facturas.view",
  "description": "Ver facturas MBA3",
  "module": "mba3-consultas"
}
```

#### Permiso 2: Ejecutar Procesos

```http
POST http://localhost:5000/api/permissions
Authorization: Bearer <tu-admin-token>
Content-Type: application/json

{
  "key": "mba3-consultas.proceso.execute",
  "description": "Ejecutar procesos MBA3 (consultar, migrar, procesar OC, integrar SAP)",
  "module": "mba3-consultas"
}
```

#### Permiso 3: Ver Órdenes de Compra

```http
POST http://localhost:5000/api/permissions
Authorization: Bearer <tu-admin-token>
Content-Type: application/json

{
  "key": "mba3-consultas.ordenes-compra.view",
  "description": "Ver órdenes de compra",
  "module": "mba3-consultas"
}
```

### Paso 3: Asignar Permisos a Roles

Después de registrar los permisos, obtendrás un `permissionId` en cada respuesta. Usa esos IDs para asignar los permisos a los roles correspondientes.

#### Asignar Permiso 1 a un Rol

```http
POST http://localhost:5000/api/permissions/assign
Authorization: Bearer <tu-admin-token>
Content-Type: application/json

{
  "roleName": "Ventas",
  "permissionId": <ID-del-permiso-1>
}
```

#### Asignar Permiso 2 a un Rol

```http
POST http://localhost:5000/api/permissions/assign
Authorization: Bearer <tu-admin-token>
Content-Type: application/json

{
  "roleName": "Ventas",
  "permissionId": <ID-del-permiso-2>
}
```

#### Asignar Permiso 3 a un Rol

```http
POST http://localhost:5000/api/permissions/assign
Authorization: Bearer <tu-admin-token>
Content-Type: application/json

{
  "roleName": "Ventas",
  "permissionId": <ID-del-permiso-3>
}
```

## 📊 Mapeo de Endpoints a Permisos

| Endpoint | Método | Permiso Requerido |
|----------|--------|-------------------|
| `/despachos/count` | GET | `mba3-consultas.facturas.view` |
| `/consultar` | GET | `mba3-consultas.proceso.execute` |
| `/migrar` | GET | `mba3-consultas.proceso.execute` |
| `/pruebas` | GET | `mba3-consultas.proceso.execute` |
| `/procesar-oc` | GET | `mba3-consultas.proceso.execute` |
| `/integrar-sap` | POST | `mba3-consultas.proceso.execute` |
| `/ordenes-compra` | GET | `mba3-consultas.ordenes-compra.view` |
| `/health` | GET | Sin autenticación (público) |

## ✅ Verificación

Después de registrar y asignar los permisos:

1. **El usuario debe hacer login nuevamente** para obtener un nuevo token con los permisos actualizados
2. **Probar los endpoints** desde el frontend o Postman
3. **Verificar que no aparezcan errores 403**

## 🔍 Solución de Problemas

### Error 403 (Forbidden)
- **Causa**: El usuario no tiene el permiso requerido
- **Solución**: Verificar que el permiso esté asignado al rol del usuario y que el usuario haya hecho login nuevamente

### Error 401 (Unauthorized)
- **Causa**: Token JWT inválido o expirado
- **Solución**: Hacer login nuevamente para obtener un nuevo token

### El permiso no aparece en el token
- **Causa**: El usuario no hizo login después de asignar el permiso
- **Solución**: Cerrar sesión y hacer login nuevamente

## 📝 Notas

- Los permisos deben registrarse **una sola vez** en el Core
- Los permisos se asignan a **roles**, no directamente a usuarios
- Los usuarios obtienen permisos a través de sus roles
- Después de asignar permisos, los usuarios deben **hacer login nuevamente** para obtener tokens actualizados



