# API Documentation
This project uses Django RestFramework Spectacular to serve a UI where you can see the endpoints available in your API

## Usage 
To generate your API schema, you can use the following command in the root of the project:
````shell
./backend/manage.py spectacular --file schema.yml
````
this will generate a schema.yml file with an OPEN API 2.0 schema for your API. You can also validate your schema by adding the flag –validate.

## Customization
### Customization via @extend_schema
- Most of the customizations should be covered by the extend_schema decorator which you can import from drf_spectacular.utils.
You can customize your documentation by decorating either an APIView, a Viewset or a function based view. If you want to annotate methods that are provided by the base classes of a view, you have nothing to attach @extend_schema to.
In those instances you can use @extend_schema_view to conveniently annotate the default implementations:

````python
def list(self, request, *args, **kwargs):
    """
    changed description
    """
    queryset = self.filter_queryset(self.get_queryset())
    serializer = self.get_serializer(queryset, many=True)
    return Response(serializer.data)
````
- Or by using the extend_schema decorator:
````python
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
````
- You can add extra parameters to your endpoint:
````python
@extend_schema(parameters=[
    OpenApiParameter(name="some parameter", description="some desc", required=False, type=str)])
def list(self, request, *args, **kwargs):
    queryset = self.filter_queryset(self.get_queryset())
    serializer = self.get_serializer(queryset, many=True)
    return Response(serializer.data)
````
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