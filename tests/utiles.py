PASSWORD_ADMIN = "clave-admin-1"


def con_token(token):
    return {"Authorization": f"Bearer {token}"}
