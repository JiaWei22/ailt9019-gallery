from django.contrib.auth.hashers import PBKDF2PasswordHasher


class IssuedPasswordHasher(PBKDF2PasswordHasher):
    """Faster hasher for bulk-issued course passwords.

    Django's default is about a tenth of a second per password, so replacing
    a 300-student roster spends most of a minute hashing. The iteration count
    is stored inside each hash, so passwords created earlier still verify.
    """

    iterations = 100_000
