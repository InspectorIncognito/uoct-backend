# API Documentation

This project uses Django RestFramework Spectacular to serve a UI where you can see the endpoints available in your API

## Endpoints relevantes (resumen)

### Notas generales

- **Prefijo base**: La mayoría de endpoints están bajo `/api/`.
- **Formato de timestamps**: Todos los timestamps en el backend utilizan **UTC (Coordinated Universal Time)**.
  - Formato ISO 8601: `YYYY-MM-DDTHH:MM:SSZ`
  - Ejemplo: `2024-01-26T14:30:45Z`
- **Parámetros de fecha/hora en query params**:
  - `startTime`/`endTime` (geo/speeds): `YYYY-MM-DDTHH:MM:SSZ`
  - `start_date`/`end_date` (gtfs_rt/pulses): `YYYY-MM-DDTHH:MM:SSZ`
  - `start`/`end` (gps/create): `DD/MM/YYYY HH:MM:SS`

## Manejo de Timestamps UTC y Zona Horaria

### Importante: UTC en el Backend

Todos los timestamps almacenados en la base de datos y retornados por la API están en **UTC (Coordinated Universal Time)**. No se realiza ninguna conversión de zona horaria en el servidor backend.

**Ejemplos de timestamps UTC retornados:**

- `2024-01-26T14:30:45Z` (14:30:45 UTC)
- `2024-01-26T10:15:30Z` (10:15:30 UTC)

### Conversión a America/Santiago en el Frontend

Para aplicaciones frontend que operan en **Santiago, Chile (America/Santiago)**, es **obligatorio** realizar la conversión de UTC a la zona horaria local. La diferencia horaria es:

- **Desde marzo a septiembre**: UTC - 3 horas (Hora de Invierno)
- **Desde septiembre a marzo**: UTC - 4 horas (Hora de Verano)

**Ejemplo de conversión:**

```javascript
// Timestamp UTC recibido del API
const utcTimestamp = "2024-01-26T14:30:45Z";

// Convertir a America/Santiago usando bibliotecas como date-fns o Day.js
import { utcToZonedTime, format } from "date-fns-tz";

const timeZone = "America/Santiago";
const zonedDate = utcToZonedTime(new Date(utcTimestamp), timeZone);
const formattedDate = format(zonedDate, "yyyy-MM-dd HH:mm:ss z", { timeZone });

// Resultado: "2024-01-26 10:30:45 CLT"
```

### Endpoints con soporte local

Los siguientes endpoints generan archivos CSV con timestamps **ya convertidos a America/Santiago**:

- `/api/geo/speeds/to_csv_local/`
- `/api/geo/historicSpeeds/to_csv_local/`

---

### Autenticación

| Endpoint      | Método(s) | Parámetros                                               | Respuesta                                                |
| ------------- | --------- | -------------------------------------------------------- | -------------------------------------------------------- |
| `/api/login`  | `POST`    | **Body JSON**: `username`, `password` (min 8 caracteres) | `{ username, email, first_name, last_name, token }`      |
| `/api/verify` | `POST`    | **Header**: `Authorization: Token <token>`               | Valida token y retorna datos del usuario + nuevo `token` |

### Documentación de API

| Endpoint                  | Método(s) | Parámetros | Respuesta                                               |
| ------------------------- | --------- | ---------- | ------------------------------------------------------- |
| `/api/schema/`            | `GET`     | —          | OpenAPI schema (YAML/JSON) generado por drf-spectacular |
| `/api/schema/swagger-ui/` | `GET`     | —          | Swagger UI interactivo                                  |

### Datos de velocidades (Core)

| Endpoint                                | Método(s) | Parámetros                                                                                                                       | Respuesta                                                                                                                                        |
| --------------------------------------- | --------- | -------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `/api/geo/speeds/`                      | `GET`     | **Query** (opcionales): `startTime`, `endTime` (`YYYY-MM-DDTHH:MM:SSZ`); `month` (int); `dayType`; `temporalSegment`; `ordering` | Lista de velocidades por segmento. Campos: `segment`, `temporal_segment`, `day_type`, `distance`, `time_secs`, `timestamp` (UTC), `services`     |
| `/api/geo/speeds/to_csv/`               | `GET`     | Mismos filtros que `/speeds/`                                                                                                    | Descarga CSV con timestamps en UTC: `shape`, `sequence`, `temporal_segment`, `day_type`, `distance`, `time_secs`, `timestamp`, `active_services` |
| `/api/geo/speeds/to_csv_local/`         | `GET`     | Mismos filtros que `/speeds/`                                                                                                    | Descarga CSV con timestamps convertidos a America/Santiago                                                                                       |
| `/api/geo/historicSpeeds/`              | `GET`     | **Query** (opcionales): `startTime`, `endTime`, `month`, `dayType`, `temporalSegment`, `ordering`                                | Lista de velocidades históricas por segmento/temporal (timestamps en UTC)                                                                        |
| `/api/geo/historicSpeeds/to_csv/`       | `GET`     | Mismos filtros que `/historicSpeeds/`                                                                                            | Descarga CSV con timestamps en UTC: `shape`, `sequence`, `temporal_segment`, `day_type`, `speed`                                                 |
| `/api/geo/historicSpeeds/to_csv_local/` | `GET`     | Mismos filtros que `/historicSpeeds/`                                                                                            | Descarga CSV con timestamps convertidos a America/Santiago                                                                                       |

### Alertas

| Endpoint                     | Método(s)             | Parámetros                                      | Respuesta                                                                                                                                  |
| ---------------------------- | --------------------- | ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `/api/geo/alerts/`           | `GET`                 | —                                               | Lista completa de `Alert`                                                                                                                  |
| `/api/geo/alerts/active/`    | `GET`                 | —                                               | JSON: `{ count, results }` con: `shape`, `sequence`, `speed`, `temporal_segment`, `useful`, `useless`, `date` (último rango temporal, UTC) |
| `/api/alert-threshold/`      | `GET`, `POST`         | (GET) sin parámetros; (POST) body JSON completo | GET: lista de umbrales. POST: crea nuevo umbral                                                                                            |
| `/api/alert-threshold/{id}/` | `GET`, `PUT`, `PATCH` | Path param: `id` (int)                          | Recupera/actualiza umbral específico                                                                                                       |

### GPS y Datos en tiempo real

| Endpoint                          | Método(s)     | Parámetros                                                                                                                | Respuesta                                                                                                                  |
| --------------------------------- | ------------- | ------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `/api/gtfs_rt/pulses/`            | `GET`         | **Query** (opcionales): `start_date`, `end_date` (`YYYY-MM-DDTHH:MM:SSZ`). **Default**: rango del último temporal segment | Lista de `GPSPulse`: `id`, `route_id`, `direction`, `license_plate`, `latitude`, `longitude`, `bearing`, `timestamp` (UTC) |
| `/api/gtfs_rt/pulses/to_geojson/` | `GET`         | Mismos query params que `/pulses/`                                                                                        | `FeatureCollection` (GeoJSON) con puntos GPS; `properties.service`; timestamps en UTC                                      |
| `/api/gps/create/`                | `GET`, `POST` | **Query (GET)**: `start`, `end` (`DD/MM/YYYY HH:MM:SS`); **(POST)**: body JSON completo                                   | GET: lista de registros GPS. POST: crea registro. Campos: `lat`, `lon`, `trip_id`, `datetime`                              |
| `/api/gps/create/to_geojson/`     | `GET`         | —                                                                                                                         | `FeatureCollection` de puntos GPS con `properties.trip_id`                                                                 |

### Geografía y Mapas

| Endpoint                              | Método(s) | Parámetros                        | Respuesta                                                                           |
| ------------------------------------- | --------- | --------------------------------- | ----------------------------------------------------------------------------------- |
| `/api/geo/mapData/`                   | `GET`     | —                                 | GeoJSON con data más reciente: shapes/segmentos con velocidades (timestamps en UTC) |
| `/api/geo/shape/`                     | `GET`     | —                                 | Lista de `Shape` (shapes procesados)                                                |
| `/api/geo/shape/{shape_pk}/segments/` | `GET`     | Path param: `shape_pk` (int)      | Segmentos del shape ordenados por `sequence`                                        |
| `/api/geo/services/`                  | `GET`     | —                                 | Lista de `Services` (rutas)                                                         |
| `/api/geo/gtfs_shape/`                | `GET`     | **Query**: `direction` (opcional) | Lista de `GTFSShape` (geometrías GTFS)                                              |
| `/api/geo/gtfs_shape/custom/`         | `GET`     | **Query**: `direction` (opcional) | `FeatureCollection` (GeoJSON) de shapes GTFS                                        |
| `/api/geo/stops/`                     | `GET`     | —                                 | Lista de `Stop` (paradas)                                                           |
| `/api/geo/stops/geojson/`             | `GET`     | —                                 | `FeatureCollection` con `properties.shape_pk` y `properties.segment_pk`             |
| `/api/geo/gtfs_stops/`                | `GET`     | —                                 | `FeatureCollection` (GeoJSON) de paradas GTFS                                       |

### Infraestructura

| Endpoint                   | Método(s)                               | Parámetros   | Respuesta                                   |
| -------------------------- | --------------------------------------- | ------------ | ------------------------------------------- |
| `/api/geo/traffic_signal/` | `GET`                                   | —            | Lista de `TrafficSignal` (semáforos)        |
| `/api/geo/camera/`         | `GET`                                   | —            | Lista de `Camera` (cámaras, sin paginación) |
| `/api/geo/axles/`          | `GET`, `POST`, `PUT`, `PATCH`, `DELETE` | Estándar DRF | CRUD de `Axles` (ejes) y metadatos          |

---

## Usage

To generate your API schema, you can use the following command in the root of the project:

```shell
./backend/manage.py spectacular --file schema.yml
```

this will generate a schema.yml file with an OPEN API 2.0 schema for your API. You can also validate your schema by adding the flag –validate.

## Customization

### Customization via @extend_schema

- Most of the customizations should be covered by the extend_schema decorator which you can import from drf_spectacular.utils.
  You can customize your documentation by decorating either an APIView, a Viewset or a function based view. If you want to annotate methods that are provided by the base classes of a view, you have nothing to attach @extend_schema to.
  In those instances you can use @extend_schema_view to conveniently annotate the default implementations:

```python
def list(self, request, *args, **kwargs):
    """
    changed description
    """
    queryset = self.filter_queryset(self.get_queryset())
    serializer = self.get_serializer(queryset, many=True)
    return Response(serializer.data)
```

- Or by using the extend_schema decorator:

```python
@extend_schema(description="Another description")
def list(self, request, *args, **kwargs):
    queryset = self.filter_queryset(self.get_queryset())
    serializer = self.get_serializer(queryset, many=True)
    return Response(serializer.data)
"""Alternative"""
@extend_schema_view(
    list=extend_schema(description='Another desc')
)
class ServiceUnitViewSet(mixins.ListModelMixin,
                         mixins.CreateModelMixin,
                         mixins.UpdateModelMixin,
                         viewsets.GenericViewSet)
```

- You can add extra parameters to your endpoint:

```python
@extend_schema(parameters=[
    OpenApiParameter(name="some parameter", description="some desc", required=False, type=str)])
def list(self, request, *args, **kwargs):
    queryset = self.filter_queryset(self.get_queryset())
    serializer = self.get_serializer(queryset, many=True)
    return Response(serializer.data)
```

- Assign request/response examples

```python
@extend_schema(examples=[OpenApiExample(
                'Service Unit',
                description='A service unit ex',
                value={"id": 1,"name": "Unidad de servicio", "unit_number": 2,"unit_code": "U2", "logo": "image to upload", "created_at": "20-10-2022"}
            , response_only=True)],
)
```

- And more. In the following example you can see the different customizations you can do to your API documentation with @extend_schema:

```python
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from drf_spectacular.types import OpenApiTypes

class AlbumViewset(viewset.ModelViewset):
    serializer_class = AlbumSerializer

    @extend_schema(
        request=AlbumCreationSerializer,
        responses={201: AlbumSerializer},
    )
    def create(self, request):
        # your non-standard behaviour
        return super().create(request)

    @extend_schema(
        # extra parameters added to the schema
        parameters=[
            OpenApiParameter(name='artist', description='Filter by artist', required=False, type=str),
            OpenApiParameter(
                name='release',
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description='Filter by release date',
                examples=[
                    OpenApiExample(
                        'Example 1',
                        summary='short optional summary',
                        description='longer description',
                        value='1993-08-23'
                    ),
                    ...
                ],
            ),
        ],
        # override default docstring extraction
        description='More descriptive text',
        # provide Authentication class that deviates from the views default
        auth=None,
        # change the auto-generated operation name
        operation_id=None,

        # or even completely override what AutoSchema would generate. Provide         raw Open API spec as Dict.
        operation=None,
        # attach request/response examples to the operation.
        examples=[
            OpenApiExample(
                'Example 1',
                description='longer description',
                value=...
            ),
            ...
        ],
    )
    def list(self, request):
        # your non-standard behaviour
        return super().list(request)

    @extend_schema(
        request=AlbumLikeSerializer,
        responses={204: None},
        methods=["POST"]
    )
    @extend_schema(description='Override a specific method', methods=["GET"])
    @action(detail=True, methods=['post', 'get'])
    def set_password(self, request, pk=None):
        # your action behavior

```

## Further Customization

If that is not enough, you can further customize it. You can check all available customizations here: [In depth customization](https://drf-spectacular.readthedocs.io/en/latest/customization.html).
