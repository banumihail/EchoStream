"""
Generate a self-signed TLS certificate for local development (Phase 8).

Writes certs/localhost-cert.pem and certs/localhost-key.pem, valid for
localhost / 127.0.0.1 / ::1. The traffic encryption is identical to a
CA-issued cert; the only difference is the browser shows a one-time
"not private" warning because no public authority vouches for it.

Run:  python tools/gen_cert.py
"""
import datetime
import ipaddress
import os

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CERT_DIR = os.path.join(ROOT, "certs")
os.makedirs(CERT_DIR, exist_ok=True)
CERT_PATH = os.path.join(CERT_DIR, "localhost-cert.pem")
KEY_PATH = os.path.join(CERT_DIR, "localhost-key.pem")

key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

subject = issuer = x509.Name([
    x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
    x509.NameAttribute(NameOID.ORGANIZATION_NAME, "EchoStream Dev"),
])

now = datetime.datetime.now(datetime.timezone.utc)
cert = (
    x509.CertificateBuilder()
    .subject_name(subject)
    .issuer_name(issuer)
    .public_key(key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now - datetime.timedelta(days=1))
    .not_valid_after(now + datetime.timedelta(days=365))
    .add_extension(
        x509.SubjectAlternativeName([
            x509.DNSName("localhost"),
            x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
            x509.IPAddress(ipaddress.IPv6Address("::1")),
        ]),
        critical=False,
    )
    .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
    .sign(key, hashes.SHA256())
)

with open(KEY_PATH, "wb") as f:
    f.write(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ))

with open(CERT_PATH, "wb") as f:
    f.write(cert.public_bytes(serialization.Encoding.PEM))

print(f"[OK] wrote {CERT_PATH}")
print(f"[OK] wrote {KEY_PATH}")
print("Valid for: localhost, 127.0.0.1, ::1 — 365 days")
