from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

CODE_BY_STATUS = {
    status.HTTP_400_BAD_REQUEST: "bad_request",
    status.HTTP_401_UNAUTHORIZED: "unauthorized",
    status.HTTP_403_FORBIDDEN: "forbidden",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_409_CONFLICT: "conflict",
    status.HTTP_422_UNPROCESSABLE_ENTITY: "validation_error",
}


def viralcutter_exception_handler(exc, context):
    """Unified JSON error envelope: {error, code, detail}."""
    response = exception_handler(exc, context)
    if response is None:
        return None

    code = CODE_BY_STATUS.get(response.status_code, "error")
    detail = response.data

    body = {"error": True, "code": code, "detail": detail}
    return Response(body, status=response.status_code)